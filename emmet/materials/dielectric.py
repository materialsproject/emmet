import logging
import numpy as np
from datetime import datetime
from itertools import combinations

from pymongo import ASCENDING

from pymatgen import Structure
from pymatgen.analysis.elasticity.tensors import Tensor
from pymatgen.analysis.piezo import PiezoTensor

from maggma.builder import Builder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class DielectricBuilder(Builder):
    def __init__(self, materials, dielectric, min_band_gap=0.1, query={}, **kwargs):
        """
        Creates a dielectric collection for materials

        Args:
            materials (Store): Store of materials documents to match to
            dielectric (Store): Store of dielectric properties
            min_band_gap (float): minimum band gap for a material to look for a dielectric calculation to build
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.dielectric = dielectric
        self.min_band_gap = min_band_gap
        self.query = query

        super().__init__(sources=[materials],
                         targets=[dielectric],
                         **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Dielectric Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        q = dict(self.query)
        q.update(self.materials.lu_filter(self.dielectric))
        q["dielectric"] = {"$exists": 1}
        mats = list(self.materials.find(q, {"material_id": 1}))

        self.logger.info("Found {} new materials for dielectric data".format(len(mats)))

        for m in mats:
            mat = self.materials().find_one(m, {"material_id": 1, "dielectric": 1, "piezo": 1, "structure": 1})
            yield mat

    def process_item(self, item):
        """
        Process the tasks and materials into a dielectrics collection

        Args:
            item dict: a dict of material_id, structure, and tasks

        Returns:
            dict: a dieletrics dictionary  
        """

        def poly(matrix):
            diags = np.diagonal(matrix)
            return np.prod(diags) / np.sum(np.prod(comb) for comb in combinations(diags, 2))

        d = {
            "material_id": item["material_id"]
        }

        structure = Structure.from_dict(item["structure"])

        if item.get("dielectric") is not None:
            ionic = Tensor(d["dielectric"]["ionic"])
            static = Tensor(d["dielectric"]["static"])
            total = ionic + static

            d["dielectric"] = {
                "total": total.symmetrized.fit_to_structure(structure).convert_to_ieee(structure),
                "ionic": ionic.symmetrized.fit_to_structure(structure).convert_to_ieee(structure),
                "static": static.symmetrized.fit_to_structure(structure).convert_to_ieee(structure),
                "e_total": poly(total),
                "e_ionic": poly(ionic),
                "e_static": poly(static)
            }

        # Update piezo if non_centrosymmetric
        if item.get("piezo") is not None:
            static = PiezoTensor.from_voigt(np.array(item['piezo']["piezo_tensor"]))
            ionic = PiezoTensor.from_voigt(np.array(item['piezo']["piezo_ionic_tensor"]))
            total = ionic + static

            d["piezo"] = {
                "total": total.symmetrized.fit_to_structure(structure).convert_to_ieee(structure).voigt,
                "ionic": ionic.symmetrized.fit_to_structure(structure).convert_to_ieee(structure).voigt,
                "static": static.symmetrized.fit_to_structure(structure).convert_to_ieee(structure).voigt,
                "e_ij_max": np.max(total.voigt)
            }

            # TODO Add in more analysis: v_max ?
            # TODO: Add in unstable phonon mode analysis of piezoelectric for potentially ferroelectric

        if len(d) > 1:
            return d

        return None

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """

        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} dielectrics".format(len(items)))
            bulk = self.dielectric().initialize_ordered_bulk_op()

            for m in filter(None, items):
                m[self.dielectric.lu_field] = datetime.utcnow()
                bulk.find({"material_id": m["material_id"]}).upsert().replace_one(m)
            bulk.execute()
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """
        # Search index for materials
        self.materials().create_index("material_id", unique=True, background=True)
