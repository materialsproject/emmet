from datetime import datetime
from itertools import chain
from operator import itemgetter
from typing import Dict, Iterator, List, Optional

from maggma.builders import Builder
from maggma.stores import Store
from pymatgen import Structure
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher

from emmet.builders import SETTINGS
from emmet.builders.utils import maximal_spanning_non_intersecting_subsets
from emmet.core.utils import group_structures, jsanitize
from emmet.core.vasp.calc_types import CalcType, TaskType, run_type, task_type
from emmet.core.vasp.material import MaterialsDoc, PropertyOrigin
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
        tags_to_sandboxes: Optional[Dict[str, List[str]]] = None,
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
            tags_to_sandboxes: dictionary mapping sandboxes to a list of tags
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
        self.tags_to_sandboxes = tags_to_sandboxes or SETTINGS.tags_to_sandboxes
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
            "tags",
        ]

        sandboxed_tags = {
            sandbox
            for sandbox in self.tags_to_sandboxes.values()
            if self.tags_to_sandboxes is not None
        }

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

                if any(tag in sandboxed_tags for tag in t.get("tags", [])):
                    t["sandboxes"] = [
                        sandbox
                        for sandbox in self.tags_to_sandboxes
                        if any(
                            tag in t["tags"]
                            for tag in set(self.tags_to_sandboxes[sandbox])
                        )
                    ]
                else:
                    t["sandboxes"] = ["core"]

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

        materials = [MaterialsDoc.from_tasks(group) for group in grouped_tasks]
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
