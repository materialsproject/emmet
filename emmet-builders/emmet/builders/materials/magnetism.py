import os.path

from maggma.builders import Builder
from emmet.core.magnetism import MagnetismDoc
from pymatgen.core.structure import Structure
from emmet.core.utils import jsanitize

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>, Matthew Horton <mkhorton@lbl.gov>"

MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
MAGNETISM_SCHEMA = os.path.join(MODULE_DIR, "schema", "magnetism.json")


class MagneticBuilder(Builder):
    def __init__(self, materials, magnetism, tasks, **kwargs):
        """
        Creates a magnetism collection for materials

        Args:
            materials (Store): Store of materials documents to match to
            magnetism (Store): Store of magnetism properties

        """

        self.materials = materials
        self.magnetism = magnetism
        self.tasks = tasks

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
        mag_ids = self.dielectric.distinct(self.magnetism.key)

        mats_set = set(
            self.magnetism.newer_in(target=self.materials, criteria=q, exhaustive=True)
        ) | (set(mat_ids) - set(mag_ids))

        mats = [mat for mat in mats_set]

        self.logger.info("Processing {} materials for magnetism data".format(len(mats)))

        self.total = len(mats)

        for mat in mats:
            mat_doc = self.materials.query_one(
                {self.materials.key: mat},
                [
                    self.materials.key,
                    "structure",
                    "deprecated",
                    "origins",
                    "last_updated",
                ],
            )

            task_doc = None

            origins = mat_doc.get("origins", [])

            if len(origins) > 0:
                for entry in origins:
                    if entry["name"] == "structure":
                        task_doc = self.tasks.query_one(
                            {self.tasks.key: entry["task_id"]},
                            ["calcs_reversed", "task_id", "last_updated"],
                        )
                        break

            if mat_doc is not None and task_doc is not None:
                mat_doc["task_id"] = task_doc["task_id"]
                mat_doc["total_magnetization"] = abs(
                    task_doc["calcs_reversed"][-1]["output"]["outcar"][
                        "total_magnetization"
                    ]
                )
                mat["task_updated"] = task_doc["last_updated"]
                yield mat_doc
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
            meta_structure=structure,
            material_id=mpid,
            origins=[origin_entry],
            deprecated=item["deprecated"],
            last_updated=item["last_updated"],
        )

        return jsanitize(doc.dict(), allow_bson=True)
