import numpy as np
from typing import Optional, Dict
from maggma.stores import Store
from maggma.builders import Builder
from emmet.core.magnetism import MagnetismDoc
from pymatgen.core.structure import Structure
from emmet.core.utils import jsanitize

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>, Matthew Horton <mkhorton@lbl.gov>"


class MagneticBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        magnetism: Store,
        tasks: Store,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Creates a magnetism collection for materials

        Args:
            materials (Store): Store of materials documents to match to
            magnetism (Store): Store of magnetism properties

        """

        self.materials = materials
        self.magnetism = magnetism
        self.tasks = tasks
        self.query = query or {}
        self.kwargs = kwargs

        self.materials.key = "material_id"
        self.tasks.key = "task_id"
        self.magnetism.key = "material_id"

        super().__init__(sources=[materials, tasks], targets=[magnetism], **kwargs)

    def get_items(self):
        """
        Gets all items to process

        Returns:
            Generator or list relevant tasks and materials to process
        """

        self.logger.info("Magnetism Builder Started")

        q = dict(self.query)

        mat_ids = self.materials.distinct(self.materials.key, criteria=q)
        mag_ids = self.magnetism.distinct(self.magnetism.key)

        mats_set = set(
            self.magnetism.newer_in(target=self.materials, criteria=q, exhaustive=True)
        ) | (set(mat_ids) - set(mag_ids))

        mats = [mat for mat in mats_set]

        self.logger.info("Processing {} materials for magnetism data".format(len(mats)))

        self.total = len(mats)

        for mat in mats:
            doc = self._get_processed_doc(mat)

            if doc is not None:
                yield doc
            else:
                pass

    def process_item(self, item):
        structure = Structure.from_dict(item["structure"])
        mpid = item["material_id"]
        origin_entry = {
            "name": "magnetism",
            "task_id": item["task_id"],
            "last_updated": item["task_updated"],
        }

        doc = MagnetismDoc.from_structure(
            structure=structure,
            material_id=mpid,
            total_magnetization=item["total_magnetization"],
            origins=[origin_entry],
            deprecated=item["deprecated"],
            last_updated=item["last_updated"],
        )

        return jsanitize(doc.dict(), allow_bson=True)

    def update_targets(self, items):
        """
        Inserts the new magnetism docs into the magnetism collection
        """
        docs = list(filter(None, items))

        if len(docs) > 0:
            self.logger.info(f"Found {len(docs)} magnetism docs to update")
            self.magnetism.update(docs)
        else:
            self.logger.info("No items to update")

    def _get_processed_doc(self, mat):

        mat_doc = self.materials.query_one(
            {self.materials.key: mat},
            [
                self.materials.key,
                "structure",
                "task_types",
                "run_types",
                "deprecated_tasks",
                "last_updated",
                "deprecated",
            ],
        )

        task_types = mat_doc["task_types"].items()

        potential_task_ids = []

        for task_id, task_type in task_types:
            if task_type in ["Structure Optimization", "Static"]:
                if task_id not in mat_doc["deprecated_tasks"]:
                    potential_task_ids.append(task_id)

        final_docs = []

        for task_id in potential_task_ids:
            task_query = self.tasks.query_one(
                properties=[
                    "last_updated",
                    "input.is_hubbard",
                    "orig_inputs.kpoints",
                    "input.parameters",
                    "output.structure",
                    "calcs_reversed",
                ],
                criteria={self.tasks.key: str(task_id)},
            )

            structure = mat_doc["structure"]

            is_hubbard = task_query["input"]["is_hubbard"]

            if (
                task_query["orig_inputs"]["kpoints"]["generation_style"] == "Monkhorst"
                or task_query["orig_inputs"]["kpoints"]["generation_style"] == "Gamma"
            ):
                nkpoints = np.prod(
                    task_query["orig_inputs"]["kpoints"]["kpoints"][0], axis=0
                )

            else:
                nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]

            lu_dt = mat_doc["last_updated"]
            task_updated = task_query["last_updated"]
            total_magnetization = task_query["calcs_reversed"][-1]["output"]["outcar"][
                "total_magnetization"
            ]

            final_docs.append(
                {
                    "task_id": task_id,
                    "is_hubbard": int(is_hubbard),
                    "nkpoints": int(nkpoints),
                    "structure": structure,
                    "deprecated": mat_doc["deprecated"],
                    "total_magnetization": total_magnetization,
                    "last_updated": lu_dt,
                    "task_updated": task_updated,
                    self.materials.key: mat_doc[self.materials.key],
                }
            )

        if len(final_docs) > 0:
            sorted_final_docs = sorted(
                final_docs,
                key=lambda entry: (
                    entry["is_hubbard"],
                    entry["nkpoints"],
                    entry["last_updated"],
                ),
                reverse=True,
            )
            return sorted_final_docs[0]
        else:
            return None
