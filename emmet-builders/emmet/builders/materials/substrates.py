from typing import Optional, Dict, Iterable
from emmet.core.mpid import MPID
from maggma.core.store import Store
from maggma.core.builder import Builder
from pymatgen.core.structure import Structure
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.core.substrates import SubstratesDoc
from emmet.core.utils import jsanitize
from maggma.utils import grouper


class SubstratesBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        substrates: Store,
        elasticity: Store,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Calculates matching substrates

        Args:
            materials (Store): Store of materials documents
            diffraction (Store): Store of substrate matches
            elasticity (Store): Store of elastic tensor documents
            substrates_file (path): file of substrates to consider
            query (dict): dictionary to limit materials to be analyzed
        """
        self.materials = materials
        self.substrates = substrates
        self.elasticity = elasticity
        self.query = query
        self.kwargs = kwargs

        # Enforce that we key on material_id
        self.materials.key = "material_id"
        self.substrates.key = "material_id"
        self.elasticity.key = "material_id"

        super().__init__(
            sources=[materials, elasticity],
            targets=[substrates],
            **kwargs,
        )

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        to_process_mat_ids = self._find_to_process()

        return [
            {"material_id": {"$in": list(chunk)}}
            for chunk in grouper(to_process_mat_ids, number_splits)
        ]

    def get_items(self):
        """
        Gets all materials that need new substrates

        Returns:
            generator of materials to calculate substrates
        """

        to_process_mat_ids = self._find_to_process()

        self.logger.info(
            "Updating all substrate calculations for {} materials".format(
                len(to_process_mat_ids)
            )
        )

        for mpid in to_process_mat_ids:
            e_tensor = self.elasticity.query_one(
                criteria={self.elasticity.key: mpid},
                properties=["elasticity", "last_updated"],
            )
            e_tensor = (
                e_tensor.get("elasticity", {}).get("elastic_tensor", None)
                if e_tensor
                else None
            )
            mat = self.materials.query_one(
                criteria={self.materials.key: mpid},
                properties=["structure", "deprecated", "material_id", "last_updated"],
            )

            yield {
                "structure": mat["structure"],
                "material_id": mat[self.materials.key],
                "elastic_tensor": e_tensor,
                "deprecated": mat["deprecated"],
                "last_updated": max(
                    mat.get("last_updated"), e_tensor.get("last_updated")
                ),
            }

    def process_item(self, item):
        """
        Calculates substrate matches for all given substrates

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            dict: a diffraction dict
        """

        mpid = MPID(item["material_id"])
        elastic_tensor = item.get("elastic_tensor", None)
        elastic_tensor = (
            ElasticTensor.from_voigt(elastic_tensor) if elastic_tensor else None
        )
        deprecated = item["deprecated"]

        self.logger.debug("Calculating substrates for {}".format(item["task_id"]))

        # Ensure we're using conventional standard to be consistent with IEEE elastic tensor setting
        film = conventional_standard_structure(item)

        substrate_doc = SubstratesDoc.from_structure(
            material_id=mpid,
            structure=film,
            elastic_tensor=elastic_tensor,
            deprecated=deprecated,
            last_updated=item["last_updated"],
        )

        return jsanitize(substrate_doc.model_dump(), allow_bson=True)

    def update_targets(self, items):
        """
        Inserts the new substrate matches into the substrates collection

        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """

        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} substrate matches".format(len(items)))
            self.substrates.update(docs=items)
        else:
            self.logger.info("No items to update")

    def ensure_indicies(self):
        """
        Ensures indicies on the substrates, materials, and elastic collections
        """
        # Search indicies for materials
        self.materials.ensure_index(self.materials.key)
        self.materials.ensure_index(self.materials.last_updated_field)

        # Search indicies for elasticity
        self.elasticity.ensure_index(self.elasticity.key)
        self.elasticity.ensure_index(self.elasticity.last_updated_field)

        # Search indicies for substrates
        self.substrates.ensure_index(self.substrates.key)
        self.substrates.ensure_index(self.substrates.last_updated_field)

    def _find_to_process(self):
        self.logger.info("Substrate Builder Started")

        self.logger.info("Setting up indicies")
        self.ensure_indicies()

        mat_keys = set(self.materials.distinct("material_id", criteria=self.query))
        updated_mats = self.materials.newer_in(self.substrates)
        e_tensor_updated_mats = self.elasticity.newer_in(self.substrates)

        # To ensure all mats are within our scope
        return set(e_tensor_updated_mats + updated_mats) & mat_keys


def conventional_standard_structure(doc):
    """Get a conventional standard structure from doc["structure"]."""
    s = Structure.from_dict(doc["structure"])
    spga = SpacegroupAnalyzer(s, symprec=0.1)
    return spga.get_conventional_standard_structure()
