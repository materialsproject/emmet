from math import ceil
from typing import Dict, Iterator, Optional

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper
from pymatgen.core.structure import Structure

from emmet.core.optimade import OptimadeMaterialsDoc
from emmet.core.utils import jsanitize


class OptimadeMaterialsBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        thermo: Store,
        optimade: Store,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Creates Optimade compatible docs containing structure and thermo data for materials

        Args:
            materials: Store of materials docs
            thermo: Store of thermo docs
            optimade: Store to update with optimade document
            query : query on materials to limit search
        """

        self.materials = materials
        self.thermo = thermo
        self.optimade = optimade
        self.query = query or {}
        self.kwargs = kwargs

        # Enforce that we key on material_id
        self.materials.key = "material_id"
        self.thermo.key = "material_id"
        self.optimade.key = "material_id"

        super().__init__(sources=[materials, thermo], targets=optimade, **kwargs)

    def prechunk(self, number_splits: int) -> Iterator[Dict]:  # pragma: no cover
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.optimade.newer_in(self.materials, criteria=q, exhaustive=True)

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.materials.key: {"$in": list(split)}}}

    def get_items(self) -> Iterator:
        """
        Gets all items to process

        Returns:
            Generator or list of relevant materials
        """

        self.logger.info("Optimade Builder Started")

        q = dict(self.query)

        q.update({"deprecated": False})

        mat_ids = self.materials.distinct(self.materials.key, criteria=q)
        opti_ids = self.optimade.distinct(self.optimade.key)

        mats_set = set(
            self.optimade.newer_in(target=self.materials, criteria=q, exhaustive=True)
        ) | (set(mat_ids) - set(opti_ids))

        mats = [mat for mat in mats_set]

        self.total = len(mats)

        self.logger.info(f"Processing {self.total} items")

        for mat in mats:
            doc = self._get_processed_doc(mat)

            if doc is not None:
                yield doc
            else:
                pass

    def process_item(self, item):
        mpid = item["mat_doc"]["material_id"]
        structure = Structure.from_dict(item["mat_doc"]["structure"])
        last_updated_structure = item["mat_doc"]["last_updated"]

        # Functional names must be lowercase to adhere to optimade spec for querying attributes
        thermo_calcs = {}
        if item["thermo_doc"]:
            for doc in item["thermo_doc"]:
                thermo_calcs[doc["thermo_type"].lower()] = {
                    "thermo_id": doc["thermo_id"],
                    "energy_above_hull": doc["energy_above_hull"],
                    "formation_energy_per_atom": doc["formation_energy_per_atom"],
                    "last_updated_thermo": doc["last_updated"],
                }

        optimade_doc = OptimadeMaterialsDoc.from_structure(
            material_id=mpid,
            structure=structure,
            last_updated_structure=last_updated_structure,
            thermo_calcs=thermo_calcs,
        )

        doc = jsanitize(optimade_doc.model_dump(), allow_bson=True)

        return doc

    def update_targets(self, items):
        """
        Inserts the new optimade docs into the optimade collection
        """
        docs = list(filter(None, items))

        if len(docs) > 0:
            self.logger.info(f"Found {len(docs)} optimade docs to update")
            self.optimade.update(docs)
        else:
            self.logger.info("No items to update")

    def _get_processed_doc(self, mat):
        mat_doc = self.materials.query_one(
            {self.materials.key: mat}, [self.materials.key, "last_updated", "structure"]
        )

        mat_doc.update(
            {
                self.materials.key: mat_doc[self.materials.key],
            }
        )

        # Query thermo store for all docs matching material_id to catch
        # multiple stability calculations for the same material_id
        thermo_docs = self.thermo.query(
            {self.thermo.key: mat},
            [
                self.thermo.key,
                "thermo_type",
                "thermo_id",
                "energy_above_hull",
                "formation_energy_per_atom",
                "last_updated",
            ],
        )

        thermo_list = [doc for doc in thermo_docs]

        if thermo_list:
            for doc in thermo_list:
                doc.update({self.thermo.key: doc[self.thermo.key]})

        combined_doc = {
            "mat_doc": mat_doc,
            "thermo_doc": None if not thermo_list else thermo_list,
        }

        return combined_doc
