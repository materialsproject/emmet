import numpy as np
from itertools import combinations

from pymatgen import Structure
from pymatgen.core.tensors import Tensor
from pymatgen.analysis.piezo import PiezoTensor
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from maggma.builder import Builder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class DielectricBuilder(Builder):
    def __init__(self, materials, dielectric, query=None, **kwargs):
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

        self.query = query if query else {}

        super().__init__(sources=[materials], targets=[dielectric], **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Dielectric Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indicies()

        q = dict(self.query)
        q.update(self.materials.lu_filter(self.dielectric))
        q["dielectric"] = {"$exists": 1}
        mats = self.materials.distinct(self.materials.key, q)

        self.logger.info("Found {} new materials for dielectric data".format(len(mats)))

        return self.materials.query(criteria=q, properties=[self.materials.key, "dielectric", "piezo", "structure"])

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

        d = {self.dielectric.key: item[self.materials.key]}

        structure = Structure.from_dict(item["structure"])

        if item.get("dielectric", False):
            ionic = Tensor(item["dielectric"]["ionic"]).symmetrized.fit_to_structure(structure).convert_to_ieee(structure)
            static = Tensor(item["dielectric"]["static"]).symmetrized.fit_to_structure(structure).convert_to_ieee(structure)
            total = ionic + static

            d["dielectric"] = {
                "total": total,
                "ionic": ionic,
                "static": static,
                "e_total": poly(total),
                "e_ionic": poly(ionic),
                "e_static": poly(static)
            }

        sga = SpacegroupAnalyzer(structure)
        # Update piezo if non_centrosymmetric
        if item.get("piezo", False) and not sga.is_laue():
            static = PiezoTensor.from_voigt(np.array(
                item['piezo']["static"])).symmetrized.fit_to_structure(structure).convert_to_ieee(structure).voigt
            ionic = PiezoTensor.from_voigt(np.array(
                item['piezo']["ionic"])).symmetrized.fit_to_structure(structure).convert_to_ieee(structure).voigt
            total = ionic + static

            directions, charges, strains = np.linalg.svd(total)

            max_index = np.argmax(np.abs(charges))
            d["piezo"] = {
                "total": total,
                "ionic": ionic,
                "static": static,
                "e_ij_max": charges[max_index],
                "max_direction": directions[max_index],
                "strain_for_max": strains[max_index]
            }

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
            self.dielectric.update(items)
        else:
            self.logger.info("No items to update")

    def ensure_indicies(self):
        """
        Ensures indexes on the materials and dielectric collection
        :return:
        """

        # Search index for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index("task_ids")

        # Search index for dielectric
        self.dielectric.ensure_index(self.dielectric.key, unique=True)
        self.dielectric.ensure_index("task_ids")
