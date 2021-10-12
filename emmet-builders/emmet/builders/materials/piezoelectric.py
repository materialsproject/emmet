from typing import Dict, Optional, List
from maggma.builders import Builder
from maggma.core import Store
import numpy as np

from pymatgen.core.structure import Structure
from emmet.core.polar import DielectricDoc, PiezoelectricDoc
from emmet.core.utils import jsanitize


class PiezoelectricBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        tasks: Store,
        piezoelectric: Store,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        self.materials = materials
        self.tasks = tasks
        self.piezoelectric = piezoelectric
        self.query = query or {}
        self.kwargs = kwargs

        self.materials.key = "material_id"
        self.tasks.key = "task_id"
        self.piezoelectric.key = "material_id"

        super().__init__(sources=[materials, tasks], targets=[piezoelectric], **kwargs)

    def get_items(self):
        """
        Gets all items to process

        Returns:
            generator or list relevant tasks and materials to process
        """

        self.logger.info("Piezoelectric Builder Started")

        q = dict(self.query)

        # Ensure no centrosymmetry
        q.update(
            {
                "symmetry.point_group": {
                    "$nin": [
                        "-1",
                        "2/m",
                        "mmm",
                        "4/m",
                        "4/mmm",
                        "-3",
                        "-3m",
                        "6/m",
                        "6/mmm",
                        "m-3",
                        "m-3m",
                    ]
                }
            }
        )

        mat_ids = self.materials.distinct(self.materials.key, criteria=q)
        piezo_ids = self.piezoelectric.distinct(self.piezoelectric.key)

        mats_set = set(
            self.piezoelectric.newer_in(
                target=self.materials, criteria=q, exhaustive=True
            )
        ) | (set(mat_ids) - set(piezo_ids))

        mats = [mat for mat in mats_set]

        self.logger.info(
            "Processing {} materials for piezoelectric data".format(len(mats))
        )

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
            "name": "piezoelectric",
            "task_id": item["task_id"],
            "last_updated": item["task_updated"],
        }

        doc = PiezoelectricDoc.from_ionic_and_electronic(
            structure=structure,
            material_id=mpid,
            origins=[origin_entry],
            deprecated=False,
            ionic=item["piezo_ionic"],
            electronic=item["piezo_static"],
            last_updated=item["updated_on"],
        )

        return jsanitize(doc.dict(), allow_bson=True)

    def update_targets(self, items):
        """
        Inserts the new dielectric docs into the dielectric collection
        """
        docs = list(filter(None, items))

        if len(docs) > 0:
            self.logger.info(f"Found {len(docs)} piezoelectric docs to update")
            self.piezoelectric.update(docs)
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
            ],
        )

        task_types = mat_doc["task_types"].items()

        potential_task_ids = []

        for task_id, task_type in task_types:
            if task_type == "DFPT Dielectric":
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
                    "output.piezo_tensor",
                    "output.piezo_ionic_tensor",
                    "output.structure",
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

            final_docs.append(
                {
                    "task_id": task_id,
                    "is_hubbard": int(is_hubbard),
                    "nkpoints": int(nkpoints),
                    "piezo_static": task_query["output"]["piezo_tensor"],
                    "piezo_ionic": task_query["output"]["piezo_ionic_tensor"],
                    "structure": structure,
                    "updated_on": lu_dt,
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
                    entry["updated_on"],
                ),
                reverse=True,
            )
            return sorted_final_docs[0]
        else:
            return None
