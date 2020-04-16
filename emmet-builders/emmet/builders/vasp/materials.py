from typing import Optional, Dict, List, Iterator
from itertools import chain
from operator import itemgetter
from datetime import datetime

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.stores import Store
from maggma.builders import Builder

from emmet.core import SETTINGS
from emmet.core.utils import (
    task_type,
    run_type,
    group_structures,
    _TASK_TYPES,
    jsanitize,
)
from emmet.core.material import MaterialsDoc, PropertyOrigin


__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class MaterialsBuilder(Builder):
    """
    The Materials Builder matches VASP task documents by structure similarity into materials
    document. The purpose of this builder is group calculations and determine the best structure.
    All other properties are derived from other builders.

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select properties from
        3.) Aggregate task documents based on strucutre similarity
        4.) Convert task docs to property docs with metadata for selection and aggregation
        5.) Select the best property doc for each property
        6.) Build material document from best property docs
        7.) Post-process material document
        8.) Validate material document

    """

    def __init__(
        self,
        tasks: Store,
        materials: Store,
        task_types: Optional[Store] = None,
        query: Optional[Dict] = None,
        allowed_task_types: Optional[List[str]] = None,
        symprec: float = SETTINGS.SYMPREC,
        ltol: float = SETTINGS.LTOL,
        stol: float = SETTINGS.STOL,
        angle_tol: float = SETTINGS.ANGLE_TOL,
        **kwargs,
    ):
        """
        Args:
            tasks: Store of task documents
            materials: Store of materials documents to generate
            query: dictionary to limit tasks to be analyzed
            allowed_task_types: list of task_types that can be processed
            symprec: tolerance for SPGLib spacegroup finding
            ltol: StructureMatcher tuning parameter for matching tasks to materials
            stol: StructureMatcher tuning parameter for matching tasks to materials
            angle_tol: StructureMatcher tuning parameter for matching tasks to materials
        """

        self.tasks = tasks
        self.materials = materials
        self.task_types = task_types
        self.allowed_task_types = allowed_task_types
        self.query = query if query else {}
        self.symprec = symprec
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.kwargs = kwargs

        sources = [tasks]
        if self.task_types:
            sources.append(self.task_types)
        super().__init__(sources=sources, targets=[materials], **kwargs)

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index(self.tasks.key, unique=True)
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")
        self.tasks.ensure_index(self.tasks.last_updated_field)

        # Search index for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index("task_ids")
        self.materials.ensure_index(self.materials.last_updated_field)

        if self.task_types:
            self.task_types.ensure_index(self.task_types.key)
            self.task_types.ensure_index("is_valid")

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into materials documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the Materials Colection

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Materials builder started")
        self.logger.info(f"Allowed task types: {self.allowed_task_types}")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime for material documents
        self.timestamp = datetime.utcnow()

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = set(self.tasks.distinct(self.tasks.key, q))
        processed_tasks = set(self.materials.distinct("task_ids"))
        to_process_tasks = all_tasks - processed_tasks
        to_process_forms = self.tasks.distinct(
            "formula_pretty", {self.tasks.key: {"$in": list(to_process_tasks)}}
        )
        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        if self.task_types:
            invalid_ids = set(
                self.task_types.distinct(self.task_types.key, {"is_valid": False})
            )
        else:
            invalid_ids = set()

        projected_fields = [
            self.tasks.last_updated_field,
            self.tasks.key,
            "formula_pretty",
            "output.energy_per_atom",
            "output.structure",
            "output.parameters",
            "orig_inputs",
            "input.structure",
        ]

        for formula in to_process_forms:
            tasks_q = dict(q)
            tasks_q["formula_pretty"] = formula
            tasks = list(
                self.tasks.query(criteria=tasks_q, properties=projected_fields)
            )
            for t in tasks:
                if t[self.tasks.key] in invalid_ids:
                    t["is_valid"] = False
                else:
                    t["is_valid"] = True

            yield tasks

    def process_item(self, tasks: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a list of materials

        Args:
            tasks [dict] : a list of task docs

        Returns:
            ([dict],list) : a list of new materials docs and a list of task_ids that were processsed
        """

        formula = tasks[0]["formula_pretty"]
        t_ids = [t[self.tasks.key] for t in tasks]
        self.logger.debug(f"Processing {formula} : {t_ids}")

        materials = []
        grouped_tasks = self.filter_and_group_tasks(tasks)

        materials = [self.make_mat(group) for group in grouped_tasks]
        self.logger.debug(f"Produced {len(materials)} materials for {formula}")

        return [mat.dict() for mat in materials if mat is not None]

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding
                processed task_ids
        """

        items = list(filter(None, chain.from_iterable(items)))

        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} materials")
            self.materials.update(docs=jsanitize(items, allow_bson=True))
        else:
            self.logger.info("No items to update")

    def filter_and_group_tasks(self, tasks: List[Dict]) -> Iterator[List[Dict]]:
        """
        Groups tasks by structure matching
        """
        allowed_task_types = self.allowed_task_types or _TASK_TYPES

        filtered_tasks = [
            task
            for task in tasks
            if any(
                allowed_type in task_type(task.get("orig_inputs", {}))
                for allowed_type in allowed_task_types
            )
        ]

        structures = []

        for idx, t in enumerate(filtered_tasks):
            s = Structure.from_dict(t["output"]["structure"])
            s.index = idx
            structures.append(s)

        grouped_structures = group_structures(
            structures,
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
            symprec=self.symprec,
        )

        for group in grouped_structures:
            yield [filtered_tasks[struc.index] for struc in group]

    def make_mat(self, task_group: List[Dict]) -> Dict:
        """
        Converts a group of tasks into one material
        """

        # Metadata
        last_updated = max(t[self.tasks.last_updated_field] for t in task_group)
        created_at = min(t[self.tasks.last_updated_field] for t in task_group)
        task_ids = list({t[self.tasks.key] for t in task_group})
        deprecated_tasks = list(
            {t[self.tasks.key] for t in task_group if not t["is_valid"]}
        )
        task_types = {
            t[self.tasks.key]: run_type(t["output"]["parameters"])
            + " "
            + task_type(t["orig_inputs"])
            for t in task_group
        }

        structure_optimizations = [
            t
            for t in task_group
            if task_type(t["orig_inputs"]) == "Structure Optimization"
        ]
        statics = [t for t in task_group if task_type(t["orig_inputs"]) == "Static"]

        # Material ID
        possible_mat_ids = [t[self.tasks.key] for t in structure_optimizations]
        possible_mat_ids = sorted(possible_mat_ids, key=ID_to_int)

        if len(possible_mat_ids) == 0:
            self.logger.error(f"Could not find a material ID for {task_ids}")
            return None
        else:
            material_id = possible_mat_ids[0]

        def _structure_eval(task: Dict):
            """
            Helper function to order structures by
            - Spin polarization
            - Special Tags
            - Forces
            """
            qual_score = {"SCAN": 3, "GGA+U": 2, "GGA": 1}

            ispin = task.get("output", {}).get("parameters", {}).get("ISPIN", 1)
            max_force = task.get("analysis", {}).get("max_force", 10000) or 10000

            special_tags = [
                task.get("output", {}).get("parameters", {}).get(tag, False)
                for tag in ["LASPH", "ADDGRID"]
            ]

            return (
                -1 * qual_score.get(run_type, 0),
                -1 * ispin,
                -1 * sum(special_tags),
                max_force,
            )

        best_structure_calc = sorted(
            structure_optimizations + statics, key=_structure_eval
        )[0]
        structure = Structure.from_dict(best_structure_calc["output"]["structure"])

        # Initial Structures
        initial_structures = [
            Structure.from_dict(t["input"]["structure"]) for t in task_group
        ]
        sm = StructureMatcher(
            ltol=0.1, stol=0.1, angle_tol=0.1, scale=False, attempt_supercell=False
        )
        initial_structures = [
            group[0] for group in sm.group_structures(initial_structures)
        ]

        # Deprecated
        deprecated = all(
            t[self.tasks.key] in deprecated_tasks for t in structure_optimizations
        )

        # Origins
        _run_type = run_type(best_structure_calc["output"]["parameters"])
        _task_type = task_type(best_structure_calc["orig_inputs"])
        origins = [
            PropertyOrigin(
                name="structure",
                task_type=f"{_run_type} {_task_type}",
                task_id=best_structure_calc[self.tasks.key],
                last_updated=best_structure_calc[self.tasks.last_updated_field],
            )
        ]

        # Warnings
        # TODO: What warning should we process?

        return MaterialsDoc.from_structure(
            structure=structure,
            material_id=material_id,
            last_updated=last_updated,
            created_at=created_at,
            task_ids=task_ids,
            task_types=task_types,
            initial_structures=initial_structures,
            deprecated=deprecated,
            deprecated_tasks=deprecated_tasks,
            origins=origins,
        )


def ID_to_int(s_id: str) -> int:
    """
    Converts a string id to tuple
    falls back to assuming ID is an Int if it can't process
    Assumes string IDs are of form "[chars]-[int]" such as mp-234
    """
    if isinstance(s_id, str):
        return (s_id.split("-")[0], int(str(s_id).split("-")[-1]))
    elif isinstance(s_id, (int, float)):
        return s_id
    else:
        return None
