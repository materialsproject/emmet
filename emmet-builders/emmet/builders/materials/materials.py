"""
Unified materials builder for tasks docs from different calc codes.
"""

from datetime import datetime
from itertools import chain, groupby
import itertools
from math import ceil
from typing import Dict, Iterable, Iterator, List, Optional, Union

from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.utils import group_structures, jsanitize
from pymatgen.core import Structure

__author__ = "Nicholas Winner <nwinner@berkeley.edu>"

SETTINGS = EmmetBuildSettings()

class MaterialsBuilder(Builder):
    """
    The Materials Builder matches VASP task documents by structure similarity into materials
    document. The purpose of this builder is group calculations and determine the best structure.
    All other properties are derived from other builders.

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select properties from
        3.) Aggregate task documents based on strucutre similarity
        4.) Create a MaterialDoc from the group of task documents
        5.) Validate material document

    """

    def __init__(
        self,
        tasks: Union[Store, Iterable[Store]],
        materials: Store,
        task_validation: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        """
        Args:
            tasks: Store of task documents
            materials: Store of materials documents to generate
            task_validation: Store for storing task validation results
            query: dictionary to limit tasks to be analyzed
            settings: EmmetSettings to use in the build process
        """

        self.tasks = tasks if isinstance(tasks, Iterable) else [tasks]
        self.materials = materials
        self.task_validation = task_validation
        self.query = query if query else {}
        self.settings = EmmetBuildSettings.autoload(settings)
        
        if len(set(t.key for t in self.tasks)) != 1:
            raise ValueError("All task stores must have the same key")

        self._tasks_key = self.tasks[0].key
        self._TASK_DOCS = dict()
        self._MAT_DOCS = dict()
        for calc_code in self.settings.ALLOWED_CALC_CODES:
            mod = __import__(f"emmet.core.{calc_code.lower()}.task", globals(), locals(), ["TaskDocument"], 0)
            self._TASK_DOCS[calc_code] = getattr(mod, "TaskDocument") 
            mod = __import__(f"emmet.core.{calc_code.lower()}.material", globals(), locals(), ["MaterialsDoc"], 0)
            self._MAT_DOCS[calc_code] = getattr(mod, "MaterialsDoc")

        self.kwargs = kwargs

        sources = self.tasks + [self.task_validation]
        super().__init__(sources=sources, targets=[materials], **kwargs)

    def _get_allowed_task_types(self, calc_code):
        if calc_code == 'vasp':
            return self.settings.VASP_ALLOWED_VASP_TYPES
        if calc_code == 'cp2k':
            return self.settings.CP2K_ALLOWED_CP2K_TYPES

    @property
    def tasks_key(self):
        return self._tasks_key

    @property
    def task_docs(self):
        """
        Returns:
            dict: A dictionary of task document classes
        """
        return self._TASK_DOCS
    
    @property
    def mat_docs(self):
        """
        Returns:
            dict: A dictionary of material document classes
        """
        return self._MAT_DOCS

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        for tasks in self.tasks:
            # Basic search index for tasks
            tasks.ensure_index("task_id")
            tasks.ensure_index("last_updated")
            tasks.ensure_index("state")
            tasks.ensure_index("formula_pretty")

        # Search index for materials
        self.materials.ensure_index("material_id")
        self.materials.ensure_index("last_updated")
        self.materials.ensure_index("task_ids")

        if self.task_validation:
            self.task_validation.ensure_index("task_id")
            self.task_validation.ensure_index("valid")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the materials builder for distributed computation"""
        temp_query = dict(self.query)
        temp_query["state"] = "successful"
        if len(self.settings.BUILD_TAGS) > 0 and len(self.settings.EXCLUDED_TAGS) > 0:
            temp_query["$and"] = [
                {"tags": {"$in": self.settings.BUILD_TAGS}},
                {"tags": {"$nin": self.settings.EXCLUDED_TAGS}},
            ]
        elif len(self.settings.BUILD_TAGS) > 0:
            temp_query["tags"] = {"$in": self.settings.BUILD_TAGS}

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(temp_query, [self.tasks.key, "formula_pretty"])
        )

        processed_tasks = set(self.materials.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_pretty"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        N = ceil(len(to_process_forms) / number_splits)

        for formula_chunk in grouper(to_process_forms, N):

            yield {"query": {"formula_pretty": {"$in": list(formula_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into materials documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the Materials Colection

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Materials builder started")
        for t in self.settings.ALLOWED_CALC_CODES:
            tt = getattr(self.settings, f"{t.upper()}_ALLOWED_TASK_TYPES") 
            self.logger.info(
                f"Allowed {t} task types: {[task_type.value for task_type in tt]}"
            )

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime for material documents
        self.timestamp = datetime.utcnow()

        # Get all processed tasks:
        temp_query = dict(self.query)
        temp_query["state"] = "successful"
        if len(self.settings.BUILD_TAGS) > 0 and len(self.settings.EXCLUDED_TAGS) > 0:
            temp_query["$and"] = [
                {"tags": {"$in": self.settings.BUILD_TAGS}},
                {"tags": {"$nin": self.settings.EXCLUDED_TAGS}},
            ]
        elif len(self.settings.BUILD_TAGS) > 0:
            temp_query["tags"] = {"$in": self.settings.BUILD_TAGS}

        self.logger.info("Finding tasks to process")
        self.logger.info(self.tasks)
        all_tasks = []
        for tasks in self.tasks:
            all_tasks.extend(
               [t for t in tasks.query(temp_query, [self.tasks_key, "formula_pretty"])] 
            )
        processed_tasks = set(self.materials.distinct("task_ids"))
        to_process_tasks = {d[self.tasks_key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_pretty"]
            for d in all_tasks
            if d[self.tasks_key] in to_process_tasks
        }

        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        validation = {
            doc[self.tasks_key]: {'valid': doc["valid"], 'calc_code': doc['calc_code']}
            for doc in self.task_validation.query(
                criteria={"calc_code": {"$exists": True}, "valid": {"$exists": True}},
                properties=[self.task_validation.key, "valid", "calc_code"],
            )
        }

        for formula in to_process_forms:
            tasks_query = dict(temp_query)
            tasks_query["formula_pretty"] = formula
            tasks = []
            for t in self.tasks:
                tasks.extend(
                    [tsk for tsk in t.query(criteria=tasks_query, properties=None)]
                )

            for t in tasks:
                t["is_valid"] = validation[t[self.tasks_key]]['valid']
                t["calc_code"] = validation[t[self.tasks_key]]['calc_code']

            yield tasks

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a list of materials

        Args:
            tasks [dict] : a list of task docs

        Returns:
            ([dict],list) : a list of new materials docs and a list of task_ids that were processsed
        """

        materials = []
        for structure_group in self.group_tasks(items):
            materials.append([])
            sorted_structures = sorted(structure_group, key=lambda x: x['calc_code'])
            self.logger.debug(f"Processing {len(sorted_structures)} tasks for a structure")

            for key, task_group in groupby(sorted_structures, key=lambda x: x["calc_code"]):
                self.logger.debug(f"Processing tasks for the calc_code {key}")

                tasks = [self.task_docs[key.upper()](**task) for task in task_group]
                formula = tasks[0].formula_pretty
                task_ids = [task.task_id for task in tasks]
                self.logger.debug(f"Processing {formula} : {task_ids}")

                try:
                    doc = self.mat_docs[key.upper()].from_tasks(
                            tasks,
                            quality_scores=self.settings.VASP_QUALITY_SCORES,
                            use_statics=self.settings.VASP_USE_STATICS,
                        )
                    materials[-1].append(doc)
                    
                except Exception as e:
                    failed_ids = list({t_.task_id for t_ in tasks})
                    doc = self.mat_docs[key.upper()].construct_deprecated_material(tasks)
                    doc.warnings.append(str(e))
                    materials[-1].append(doc)
                    self.logger.warn(
                        f"Failed making material for {failed_ids}."
                        f" Inserted as deprecated Material: {doc.material_id}"
                    )

                if key == 'vasp':
                    material_id = doc.material_id
            
            for m in materials[-1]:
                m.material_id = material_id
        
        self.logger.debug(f"Produced {len(materials)} materials for {formula}")
        mats = list(itertools.chain.from_iterable(materials))
        return jsanitize([m.dict() for m in mats], allow_bson=True)

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding
                processed task_ids
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        for item in docs:
            item.update({"_bt": self.timestamp})

        material_ids = list({item["material_id"] for item in docs})

        if len(items) > 0:
            self.logger.info(f"Updating {len(docs)} materials")
            self.materials.remove_docs({self.materials.key: {"$in": material_ids}})
            self.materials.update(
                docs=docs, key=["material_id"],
            )
        else:
            self.logger.info("No items to update")

    def group_tasks(
        self, tasks: List
    ) -> Iterator[List]:
        """
        Groups tasks by structure matching
        """
        structures = []

        for idx, task in enumerate(tasks):
            s = Structure.from_dict(task['output']['structure'])
            s.index: int = idx  # type: ignore
            structures.append(s)

        grouped_structures = group_structures(
            structures,
            ltol=self.settings.LTOL,
            stol=self.settings.STOL,
            angle_tol=self.settings.ANGLE_TOL,
            symprec=self.settings.SYMPREC,
        )
        for group in grouped_structures:
            grouped_tasks = [tasks[struc.index] for struc in group]  # type: ignore
            yield grouped_tasks
