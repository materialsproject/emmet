from datetime import datetime
from itertools import chain
from math import ceil
from typing import Dict, Iterable, Iterator, List, Optional, Union

import pandas as pd
from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.utils import group_structures, jsanitize, undeform_structure
from emmet.core.vasp.calc_types import TaskType
from emmet.core.vasp.material import MaterialsDoc
from emmet.core.vasp.task_valid import TaskDocument

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

SETTINGS = EmmetBuildSettings()


class MaterialsBuilder(Builder):
    """
    The Materials Builder matches VASP task documents by structure similarity into
    materials document. The purpose of this builder is group calculations and determine
    the best structure. All other properties are derived from other builders.

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select properties from
        3.) Aggregate task documents based on structure similarity
        4.) Create a MaterialDoc from the group of task documents
        5.) Validate material document

    """

    def __init__(
        self,
        source_keys: Dict[str, Store],
        target_keys: Dict[str, Store],
        chunk_size: int = 200,
        allow_bson=True,
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
        self.source_keys = source_keys
        self.target_keys = target_keys

        self.tasks = source_keys["tasks"]
        self.task_validation = (
            source_keys["task_validation"] if "task_validation" in source_keys else None
        )
        self.materials = target_keys["materials"]
        self.query = query if query else {}
        self.temp_query = {}
        self.chunk_size = chunk_size
        self.allow_bson = allow_bson
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        # Save timestamp to mark buildtime for material documents
        self.timestamp = datetime.utcnow()

        sources = [self.tasks]

        if self.task_validation:
            sources.append(self.task_validation)

        super().__init__(
            sources=sources,
            targets=[self.materials],
            chunk_size=self.chunk_size,
            **kwargs,
        )

    def ensure_indexes(self):
        """
        Ensures indices on the tasks and materials collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index("task_id")
        self.tasks.ensure_index("last_updated")
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")

        # Search index for materials
        self.materials.ensure_index("material_id")
        self.materials.ensure_index("last_updated")
        self.materials.ensure_index("task_ids")

        if self.task_validation:
            self.task_validation.ensure_index("task_id")
            self.task_validation.ensure_index("valid")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the materials builder for distributed computation"""
        self.temp_query = dict(self.query)
        self.temp_query["state"] = "successful"
        if len(self.settings.BUILD_TAGS) > 0 and len(self.settings.EXCLUDED_TAGS) > 0:
            self.temp_query["$and"] = [
                {"tags": {"$in": self.settings.BUILD_TAGS}},
                {"tags": {"$nin": self.settings.EXCLUDED_TAGS}},
            ]
        elif len(self.settings.BUILD_TAGS) > 0:
            self.temp_query["tags"] = {"$in": self.settings.BUILD_TAGS}

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(self.temp_query, [self.tasks.key, "formula_pretty"])
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
        This does no datetime checking; relying on whether
        task_ids are included in the Materials Collection

        Returns:
            generator or list relevant tasks and materials to process into materials
            documents
        """

        task_types = [t.value for t in self.settings.VASP_ALLOWED_VASP_TYPES]
        self.logger.info("Materials builder started")
        self.logger.info(f"Allowed task types: {task_types}")

        self.logger.info("Setting indexes")
        # self.ensure_indexes()

        # Get all processed tasks:
        self.temp_query = dict(self.query)
        self.temp_query["state"] = "successful"
        if len(self.settings.BUILD_TAGS) > 0 and len(self.settings.EXCLUDED_TAGS) > 0:
            self.temp_query["$and"] = [
                {"tags": {"$in": self.settings.BUILD_TAGS}},
                {"tags": {"$nin": self.settings.EXCLUDED_TAGS}},
            ]
        elif len(self.settings.BUILD_TAGS) > 0:
            self.temp_query["tags"] = {"$in": self.settings.BUILD_TAGS}

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(self.temp_query, [self.tasks.key, "formula_pretty"])
        )

        processed_tasks = set(self.materials.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_pretty"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        return [
            list(to_process_forms)[i : i + self.chunk_size]
            for i in range(0, len(to_process_forms), self.chunk_size)
        ]

    def get_processed_docs(self, mats):
        for store in self.source_keys:
            self.source_keys[store].connect()

        if self.task_validation:
            invalid_ids = {
                doc[self.tasks.key]
                for doc in self.task_validation.query(
                    {"valid": False}, [self.task_validation.key]
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
            # needed for run_type and task_type
            "calcs_reversed.input.parameters",
            "calcs_reversed.input.incar",
            "orig_inputs",
            "input.structure",
            # needed for entry from task_doc
            "output.energy",
            "input.is_hubbard",
            "input.hubbards",
            "input.potcar_spec",
            # needed for transform deformation structure back for grouping
            "transformations",
            # misc info for materials doc
            "tags",
        ]

        all_docs = []

        for formula in mats:
            tasks_query = dict(self.temp_query)
            tasks_query["formula_pretty"] = formula
            tasks = list(
                self.tasks.query(criteria=tasks_query, properties=projected_fields)
            )
            for t in tasks:
                t["is_valid"] = t[self.tasks.key] not in invalid_ids

            all_docs.append(tasks)

        return all_docs

    def process_item(self, items: List[List[Dict]]) -> List[Dict]:
        """
        Process the tasks into a list of materials

        Args:
            tasks [dict]: a list of lists containing task docs

        Returns:
            ([dict],list): a list of new materials docs and a list of task_ids that
                were processed
        """
        docs = []
        for item in items:
            if not item:
                continue

            tasks = [TaskDocument(**task) for task in item]
            formula = tasks[0].formula_pretty
            task_ids = [task.task_id for task in tasks]

            # not all tasks contains transformation information
            task_transformations = [task.get("transformations", None) for task in item]

            self.logger.debug(f"Processing {formula}: {task_ids}")

            grouped_tasks = self.filter_and_group_tasks(tasks, task_transformations)
            materials = []
            for group in grouped_tasks:
                commercial_license = True
                for task_doc in group:
                    if set(task_doc.tags).intersection(
                        set(self.settings.NON_COMMERCIAL_TAGS)
                    ):
                        commercial_license = False
                        break
                try:
                    materials.append(
                        MaterialsDoc.from_tasks(
                            group,
                            structure_quality_scores=self.settings.VASP_STRUCTURE_QUALITY_SCORES,
                            use_statics=self.settings.VASP_USE_STATICS,
                            commercial_license=commercial_license,
                        )
                    )
                except Exception as e:
                    failed_ids = list({t_.task_id for t_ in group})
                    doc = MaterialsDoc.construct_deprecated_material(
                        group, commercial_license
                    )
                    doc.warnings.append(str(e))
                    materials.append(doc)
                    self.logger.warn(
                        f"Failed making material for {failed_ids}."
                        f" Inserted as deprecated Material: {doc.material_id}"
                    )

            self.logger.debug(f"Produced {len(materials)} materials for {formula}")

            docs.append(
                jsanitize([mat.model_dump() for mat in materials], allow_bson=True)
            )

        return docs

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the
                corresponding processed task_ids
        """
        if not items:
            return

        self.materials.connect()

        docs = list(chain.from_iterable(items))  # type: ignore

        for doc in docs:
            doc.update({"_bt": self.timestamp})

        material_ids = list({doc["material_id"] for doc in docs})

        if len(docs) > 0:
            self.logger.info(f"Updating {len(docs)} materials")
            self.materials.remove_docs({self.materials.key: {"$in": material_ids}})
            self.materials.update(docs=docs, key=["material_id"])
        else:
            self.logger.info("No items to update")

        self.materials.close()

    def filter_and_group_tasks(
        self, tasks: List[TaskDocument], task_transformations: List[Union[Dict, None]]
    ) -> Iterator[List[TaskDocument]]:
        """
        Groups tasks by structure matching
        """

        filtered_tasks = []
        filtered_transformations = []
        for task, transformations in zip(tasks, task_transformations):
            if any(
                allowed_type == task.task_type
                for allowed_type in self.settings.VASP_ALLOWED_VASP_TYPES
            ):
                filtered_tasks.append(task)
                filtered_transformations.append(transformations)

        structures = []
        for idx, (task, transformations) in enumerate(
            zip(filtered_tasks, filtered_transformations)
        ):
            if task.task_type == TaskType.Deformation:
                if (
                    transformations is None
                ):  # Do not include deformed tasks without transformation information
                    self.logger.debug(
                        "Cannot find transformation for deformation task {}. Excluding task.".format(
                            task.task_id
                        )
                    )
                    continue
                else:
                    s = undeform_structure(task.input.structure, transformations)

            else:
                s = task.output.structure
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
            grouped_tasks = [filtered_tasks[struct.index] for struct in group]  # type: ignore
            yield grouped_tasks
