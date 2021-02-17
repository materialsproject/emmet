from datetime import datetime
from itertools import chain
from operator import itemgetter
from typing import Dict, Iterator, List, Optional

from maggma.builders import Builder
from maggma.stores import Store
from pymatgen import Structure
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher

from emmet.builders.utils import maximal_spanning_non_intersecting_subsets
from emmet.core import SETTINGS
from emmet.core.utils import group_structures, jsanitize
from emmet.core.vasp.calc_types import TaskType
from emmet.core.vasp.material import MaterialsDoc
from emmet.core.vasp.task import TaskDocument
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
        self.allowed_task_types = (
            [t.value for t in TaskType]
            if allowed_task_types is None
            else allowed_task_types
        )

        self._allowed_task_types = {TaskType(t) for t in self.allowed_task_types}

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
        self.tasks.ensure_index("task_id")
        self.tasks.ensure_index("last_updated")
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")

        # Search index for materials
        self.materials.ensure_index("material_id")
        self.materials.ensure_index("last_updated")
        self.materials.ensure_index("sandboxes")
        self.materials.ensure_index("task_ids")

        if self.task_validation:
            self.task_validation.ensure_index("task_id")
            self.task_validation.ensure_index("valid")

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into materials documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the Materials Colection

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Materials builder started")
        self.logger.info(
            f"Allowed task types: {[task_type.value for task_type in self._allowed_task_types]}"
        )

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
            "last_updated",
            "completed_at",
            "task_id",
            "formula_pretty",
            "output.energy_per_atom",
            "output.structure",
            "input.parameters",
            "orig_inputs",
            "input.structure",
            "tags",
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

        tasks = [TaskDocument(**task) for task in tasks]
        formula = tasks[0].formula_pretty
        task_ids = [task.task_id for task in tasks]
        self.logger.debug(f"Processing {formula} : {task_ids}")

        grouped_tasks = self.filter_and_group_tasks(tasks)
        materials = []
        for group in grouped_tasks:
            try:
                materials.append(MaterialsDoc.from_tasks(group))
            except Exception:
                failed_ids = list({t_.task_id for t_ in group})
                self.logger.warn(
                    f"No valid ids found among ids {failed_ids}. This can be the case if the required "
                    "calculation types are missing from your tasks database."
                )
        self.logger.debug(f"Produced {len(materials)} materials for {formula}")

        return [mat.dict() for mat in materials]

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

        material_ids = list({item["material_id"] for item in items})

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} materials")
            self.materials.remove_docs({self.materials.key: {"$in": material_ids}})
            self.materials.update(
                docs=jsanitize(items, allow_bson=True),
                key=["material_id"],
            )
        else:
            self.logger.info("No items to update")

    def filter_and_group_tasks(self, tasks: List[TaskDocument]) -> Iterator[List[Dict]]:
        """
        Groups tasks by structure matching
        """

        filtered_tasks = [
            task
            for task in tasks
            if any(
                allowed_type is task.task_type
                for allowed_type in self._allowed_task_types
            )
        ]

        structures = []

        for idx, task in enumerate(filtered_tasks):
            s = task.output.structure
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
            yield grouped_tasks
