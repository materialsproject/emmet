from typing import Optional, Dict, List, Iterator
from itertools import chain
from operator import itemgetter
from datetime import datetime

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from pymatgen.analysis.structure_analyzer import oxide_type


from maggma.stores import Store
from maggma.builders import Builder

from emmet.builders import SETTINGS
from emmet.core.vasp.calc_types import task_type, run_type, TaskType, CalcType

from emmet.core.utils import group_structures, jsanitize

from emmet.core.vasp.material import MaterialsDoc, PropertyOrigin
from emmet.builders.utils import maximal_spanning_non_intersecting_subsets
from emmet.stubs import ComputedEntry


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
        task_validation: Optional[Store] = None,
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
        self.task_validation = task_validation
        self.allowed_task_types = {TaskType(t) for t in allowed_task_types} or set(
            TaskType
        )
        self.query = query if query else {}
        self.symprec = symprec
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.kwargs = kwargs

        sources = [tasks]
        if self.task_validation:
            sources.append(self.task_validation)
        super().__init__(sources=sources, targets=[materials], **kwargs)

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index(self.tasks.key)
        self.tasks.ensure_index(self.tasks.last_updated_field)
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")

        # Search index for materials
        self.materials.ensure_index(self.materials.key)
        self.materials.ensure_index(self.materials.last_updated_field)
        self.materials.ensure_index("sandboxes")
        self.materials.ensure_index("task_ids")

        if self.task_validation:
            self.task_validation.ensure_index(self.task_validation.key)
            self.task_validation.ensure_index("is_valid")

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
        temp_query = dict(self.query)
        temp_query["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = {
            doc[self.tasks.key]
            for doc in self.tasks.query(temp_query, [self.tasks.key])
        }
        processed_tasks = {
            t_id
            for d in self.materials.query({}, ["task_ids"])
            for t_id in d.get("task_ids", [])
        }
        to_process_tasks = all_tasks - processed_tasks
        to_process_forms = self.tasks.distinct(
            "formula_pretty", {self.tasks.key: {"$in": list(to_process_tasks)}}
        )
        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        if self.task_validation:
            invalid_ids = {
                doc[self.tasks.key]
                for doc in self.task_validation.query(
                    {"is_valid": False}, [self.task_validation.key]
                )
            }
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
            "sandboxes",
        ]

        for formula in to_process_forms:
            tasks_query = dict(temp_query)
            tasks_query["formula_pretty"] = formula
            tasks = list(
                self.tasks.query(criteria=tasks_query, properties=projected_fields)
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
        task_ids = [task[self.tasks.key] for task in tasks]
        self.logger.debug(f"Processing {formula} : {task_ids}")

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

        material_ids = {item[self.materials.key] for item in items}

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} materials")
            self.materials.remove_docs({self.materials.key: {"$in": material_ids}})
            self.materials.update(
                docs=jsanitize(items, allow_bson=True),
                key=(self.materials.key, "sandboxes"),
            )
        else:
            self.logger.info("No items to update")

    def filter_and_group_tasks(self, tasks: List[Dict]) -> Iterator[List[Dict]]:
        """
        Groups tasks by structure matching
        """

        filtered_tasks = [
            task
            for task in tasks
            if any(
                allowed_type in task_type(task.get("orig_inputs", {}))
                for allowed_type in self.allowed_task_types
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
            grouped_tasks = [filtered_tasks[struc.index] for struc in group]
            sandboxes = [
                task["sandboxes"] for task in grouped_tasks if "sandboxes" in task
            ]

            for sbx_set in maximal_spanning_non_intersecting_subsets(sandboxes):
                yield [
                    task
                    for task in grouped_tasks
                    if len(set(task.get("sandboxes", ["core"])).intersection(sbx_set))
                    > 0
                ]

    def make_mat(self, task_group: List[Dict]) -> Dict:
        """
        Converts a group of tasks into one material
        """

        # Metadata
        last_updated = max(task[self.tasks.last_updated_field] for task in task_group)
        created_at = min(task[self.tasks.last_updated_field] for task in task_group)
        task_ids = list({task[self.tasks.key] for task in task_group})
        sandboxes = list(
            {sbxn for task in task_group for sbxn in task.get("sbxn", ["core"])}
        )

        deprecated_tasks = list(
            {
                task[self.tasks.key]
                for task in task_group
                if not task.get("is_valid", True)
            }
        )
        run_types = {
            t[self.tasks.key]: run_type(t["output"]["parameters"]) for t in task_group
        }
        task_types = {
            t[self.tasks.key]: task_type(t["orig_inputs"]) for t in task_group
        }
        calc_types = {
            task[self.tasks.key]: CalcType(
                f"{run_types[task[self.tasks.key]]}"
                + " "
                + f"{task_types[task[self.tasks.key]]}"
            )
            for task in task_group
        }

        structure_optimizations = [
            task
            for task in task_group
            if task_types[task[self.tasks.key]] == "Structure Optimization"
        ]
        statics = [
            task for task in task_group if task_types[task[self.tasks.key]] == "Static"
        ]

        # Material ID
        possible_mat_ids = [task[self.tasks.key] for task in structure_optimizations]
        possible_mat_ids = sorted(possible_mat_ids, key=ID_to_int)

        if len(possible_mat_ids) == 0:
            self.logger.error(f"Could not find a material ID for {task_ids}")
            return None
        else:
            material_id = possible_mat_ids[0]

        def _structure_eval(task: Dict):
            """
            Helper function to order structures optimziation and statics calcs by
            - Functional Type
            - Spin polarization
            - Special Tags
            - Energy
            """
            qual_score = SETTINGS.vasp_qual_scores

            ispin = task.get("output", {}).get("parameters", {}).get("ISPIN", 1)
            energy = task.get("output", {}).get("energy_per_atom", 0.0)
            task_run_type = run_type(task["output"]["parameters"])
            special_tags = [
                task.get("output", {}).get("parameters", {}).get(tag, False)
                for tag in ["LASPH"]
            ]

            is_valid = task[self.tasks.key] in deprecated_tasks

            return (
                -1 * is_valid,
                -1 * qual_score.get(task_run_type, 0),
                -1 * ispin,
                -1 * sum(special_tags),
                energy,
            )

        structure_calcs = structure_optimizations + statics
        best_structure_calc = sorted(structure_calcs, key=_structure_eval)[0]
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

        # entries
        entries = {}
        all_run_types = set(run_types.keys())
        for rt in all_run_types:
            rt_tasks = {t_id for t_id in task_ids if run_types[t_id] == rt}
            relevant_calcs = [
                doc for doc in structure_calcs if doc[self.tasks.key] in rt_tasks
            ]
            if len(relevant_calcs) > 0:
                entries[rt] = task_doc_to_entry(
                    sorted(relevant_calcs, key=_structure_eval)[0]
                )

        # Warnings
        # TODO: What warning should we process?

        return MaterialsDoc.from_structure(
            structure=structure,
            material_id=material_id,
            last_updated=last_updated,
            created_at=created_at,
            task_ids=task_ids,
            calc_types=calc_types,
            run_types=run_types,
            task_types=task_types,
            initial_structures=initial_structures,
            deprecated=deprecated,
            deprecated_tasks=deprecated_tasks,
            origins=origins,
            entries=entries,
            sandboxes=sandboxes if sandboxes else None,
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


def task_doc_to_entry(task_doc: Dict) -> ComputedEntry:
    """ Turns a Task Doc into a ComputedEntry"""

    struc = Structure.from_dict(task_doc["output"]["structure"])
    entry_dict = {
        "correction": 0.0,
        "entry_id": task_doc["task_id"],
        "composition": struc.composition,
        "energy": task_doc["output"]["energy"],
        "parameters": {
            "potcar_spec": task_doc["potcar_spec"],
            "run_type": run_type(task_doc["output"]["parameters"]),
        },
        "data": {
            "oxide_type": oxide_type(struc),
            "last_updated": task_doc["last_updated"],
        },
    }

    return ComputedEntry.from_dict(entry_dict)
