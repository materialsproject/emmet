import os
import itertools
from operator import itemgetter

from pymatgen.core import Structure
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.analysis.substrate_analyzer import SubstrateAnalyzer
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from maggma.builders import Builder
from maggma.utils import source_keys_updated

from emmet.common.utils import load_settings
__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SUBSTRATES = os.path.join(MODULE_DIR, "settings", "substrates.json")


class SubstrateBuilder(Builder):
    def __init__(self, materials, substrates, elasticity=None, substrates_file=None, query=None, **kwargs):
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
        self.substrates_file = substrates_file
        self.query = query if query else {}
        self.__settings = load_settings(self.substrates_file, DEFAULT_SUBSTRATES)

        super().__init__(sources=[materials, elasticity], targets=[substrates], **kwargs)

    def get_items(self):
        """
        Gets all materials that need new substrates

        Returns:
            generator of materials to calculate substrates
        """

        self.logger.info("Substrate Builder Started")

        self.logger.info("Setting up indicies")
        self.ensure_indicies()


        mat_keys = set(self.materials.distinct(self.materials.key, criteria=self.query))
        updated_mats = source_keys_updated(source=self.materials, target=self.substrates, query=self.query)
        e_tensor_updated_mats = source_keys_updated(source=self.elasticity, target=self.substrates)

        # To ensure all mats are within our scope
        mats = set(e_tensor_updated_mats + updated_mats) & mat_keys

        self.logger.info("Updating all substrate calculations for {} materials".format(len(mats)))

        for m in mats:
            e_tensor = self.elasticity.query_one(criteria={self.elasticity.key: m})
            e_tensor = e_tensor.get("elasticity", {}).get("elastic_tensor", None) if e_tensor else None
            mat = self.materials.query_one(
                criteria={self.materials.key: m}, properties=["structure", self.materials.key])

            yield {"structure": mat["structure"], "task_id": mat[self.materials.key], "elastic_tensor": e_tensor}

    def process_item(self, item):
        """
        Calculates substrate matches for all given substrates

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            dict: a diffraction dict
        """
        substrates = self.__settings

        elastic_tensor = item.get("elastic_tensor", None)
        elastic_tensor = ElasticTensor.from_voigt(elastic_tensor) if elastic_tensor else None

        self.logger.debug("Calculating substrates for {}".format(item["task_id"]))

        film = Structure.from_dict(item["structure"])

        all_matches = []

        sa = SubstrateAnalyzer()

        for s in substrates:

            substrate = s["structure"]

            # Calculate lowest matches and group by substrate orientation
            matches_by_orient = groupby_itemkey(
                sa.calculate(film, substrate, elastic_tensor, lowest=True), "sub_miller")

            # Find the lowest area match for each substrate orientation
            lowest_matches = [min(g, key=itemgetter("match_area")) for k, g in matches_by_orient]

            for match in lowest_matches:
                db_entry = {
                    "sub_id": s["task_id"],
                    "orient": " ".join(map(str, match["sub_miller"])),
                    "sub_form": substrate.composition.reduced_formula,
                    "film_orient": " ".join(map(str, match["film_miller"])),
                    "area": match["match_area"],
                }

                if "elastic_energy" in match:
                    db_entry["energy"] = match["elastic_energy"]
                    db_entry["strain"] = match["strain"]

                all_matches.append(db_entry)

        # Sort based on energy if an elastic tensor is present otherwise the area
        if elastic_tensor is not None:
            sort_key = itemgetter("energy")
        else:
            sort_key = itemgetter("area")

        all_matches = list(sorted(all_matches, key=sort_key))

        d = {self.substrates.key: item["task_id"], "substratess": all_matches}

        return d

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

    def get_mats_w_updated_elastic_tensors(self):
        """
        Gets all materials that have had their elastic tensor updated
        since substrates were last calculated
        """
        e_tensor_updated_mats = []
        self.logger.info("Checking for new/updated elastic tensors")
        if self.elasticity:
            # Find all materials with updated elastic tensors since the
            # substrate builder was last run and rerun all substrates for
            # analysis
            q = self.elasticity.lu_filter(self.substrates)
            e_tensor_updated_mats = self.elasticity.distinct(self.elasticity.key, criteria=q)

            # Ensure these materials are within our materials query
            # Account for when we want to constrain the materials key with the query already
            q = dict(self.query)
            if self.materials.key not in q:
                q.update({self.materials.key: {"$in": e_tensor_updated_mats}})
            else:
                temp_q = q[self.materials.key]
                q.update({"$and": [temp_q, {self.materials.key: {"$in": e_tensor_updated_mats}}]})

            e_tensor_updated_mats = self.materials.distinct(self.materials.key, criteria=q)

            self.logger.info("Found {} new/updated elastic tensors".format(len(e_tensor_updated_mats)))

        return e_tensor_updated_mats

    def get_updated_mats(self):
        """
        Gets all materials that have been updated since substrate builder was last run
        """
        self.logger.info("Checking for new/updated materials")
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.substrates))
        updated_mats = self.materials.distinct(self.materials.key, q)
        self.logger.info("Found {} new materials for substrate processing".format(len(updated_mats)))
        return updated_mats

    def ensure_indicies(self):
        """
        Ensures indicies on the substrates, materials, and elastic collections
        """
        # Search indicies for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index(self.materials.lu_field)

        # Search indicies for elasticity
        self.elasticity.ensure_index(self.elasticity.key, unique=True)
        self.elasticity.ensure_index(self.elasticity.lu_field)

        # Search indicies for substrates
        self.substrates.ensure_index(self.substrates.key, unique=True)
        self.substrates.ensure_index(self.substrates.lu_field)


def conventional_standard_structure(doc):
    """Get a conventional standard structure from doc["structure"]."""
    s = Structure.from_dict(doc["structure"])
    spga = SpacegroupAnalyzer(s, symprec=0.1)
    return spga.get_conventional_standard_structure()


def groupby_itemkey(iterable, item):
    """groupby keyed on (and pre-sorted by) itemgetter(item)."""
    itemkey = itemgetter(item)
    return itertools.groupby(sorted(iterable, key=itemkey), itemkey)
