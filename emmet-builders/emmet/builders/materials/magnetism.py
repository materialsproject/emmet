from math import ceil
from typing import Dict, Iterator, Optional

from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper
from pymatgen.core.structure import Structure

from emmet.core.magnetism import MagnetismDoc
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

    def prechunk(self, number_splits: int) -> Iterator[Dict]:  # pragma: no cover
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        q.update({"deprecated": False})

        keys = self.magnetism.newer_in(self.materials, criteria=q, exhaustive=True)

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.materials.key: {"$in": list(split)}}}

    def get_items(self):
        """
        Gets all items to process

        Returns:
            Generator or list relevant tasks and materials to process
        """

        self.logger.info("Magnetism Builder Started")

        q = dict(self.query)

        q.update({"deprecated": False})

        mat_ids = self.materials.distinct(self.materials.key, criteria=q)
        mag_ids = self.magnetism.distinct(self.magnetism.key)

        mats_set = set(self.magnetism.newer_in(target=self.materials, criteria=q, exhaustive=True)) | (
            set(mat_ids) - set(mag_ids)
        )

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
            [self.materials.key, "origins", "last_updated", "structure", "deprecated"],
        )

        for origin in mat_doc["origins"]:
            if origin["name"] == "structure":
                task_id = origin["task_id"]

        task_query = self.tasks.query_one(
            properties=["last_updated", "calcs_reversed"],
            criteria={self.tasks.key: task_id},
        )

        task_updated = task_query["last_updated"]
        total_magnetization = task_query["calcs_reversed"][-1]["output"]["outcar"]["total_magnetization"]

        mat_doc.update(
            {
                "task_id": task_id,
                "total_magnetization": total_magnetization,
                "task_updated": task_updated,
                self.materials.key: mat_doc[self.materials.key],
            }
        )

        return mat_doc
