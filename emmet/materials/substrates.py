import os
import itertools
from operator import itemgetter

from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.analysis.substrate_analyzer import SubstrateAnalyzer
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pydash import get

from maggma.builder import Builder

from emmet.common.utils import load_settings
__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
default_substrate_settings = os.path.join(
    module_dir, "settings", "substrates.yaml")


class SubstrateBuilder(Builder):

    def __init__(self, materials, substrates, elasticity=None, substrate_settings=None,
                 query=None, **kwargs):
        """
        Calculates matching substrates for

        Args:
            materials (Store): Store of materials documents
            diffraction (Store): Store of substrate matches
            elasticity (Store): Store of elastic tensor documents
            substrate_settings (path): Store of xrd settings
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.substrates = substrates
        self.elasticity = elasticity
        self.substrate_settings = substrate_settings
        self.query = query if query else {}
        self.__settings = load_settings(
            self.substrate_settings, default_substrate_settings)

        super().__init__(sources=[materials],
                         targets=[substrates],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need new substrates

        Returns:
            generator of materials to calculate substrates
        """

        self.logger.info("Substrate Builder Started")

        self.logger.info("Getting substrate structures")
        self.load_substrate_mats()

        e_tensor_updated_mats = self.get_mats_w_updated_elastic_tensors()
        updated_mats = self.get_updated_mats()
        updated_substrates = self.get_updated_substrates()

        mats = set(e_tensor_updated_mats + updated_mats)
        self.logger.info(
            "Updating all substrate calculations for {} materials".format(len(mats)))
        self.yield_mats(mats, self.substrate_mats)

        self.logger.info(
            "Updating remaining materials for {} new/updated substrates".format(len(updated_substrates)))
        updated_substrate_mats = [s for s in self.substrate_mats if s[
            self.materials.key] in updated_substrates]
        remaining_mats = set(self.materials.distinct(
            self.materials.key, self.query)) - set(mats)
        self.yield_mats(remaining_mats, updated_substrate_mats)

    def process_item(self, item):
        """
        Calculates substrate matches for all given substrates

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            dict: a diffraction dict
        """
        material = item["material"]
        elastic_tensor = item.get("elastic_tensor", None)
        substrates = item["substrates"]

        self.logger.debug("Calculating substrates for {}".format(
            get(self.materials.key, material)))

        film = Structure.from_dict(material["structure"])

        all_matches = []

        sa = SubstrateAnalyzer()

        for s in substrates:

            substrate = Structure.from_dict(s["structure"])

            # Calculate all matches and group by substrate orientation
            matches_by_orient = groupby_itemkey(
                sa.calculate(film, substrate, elastic_tensor, lowest=True),
                "sub_miller")

            # Find the lowest area match for each substrate orientation
            lowest_matches = [min(g, key=itemgetter("match_area"))
                              for k, g in matches_by_orient]

            for match in lowest_matches:
                db_entry = {
                    "film_id": material[self.materials.key],
                    "sub_id": s[self.materials.key],
                    "orient": " ".join(map(str, match["sub_miller"])),
                    "sub_form": substrate.composition.reduced_formula,
                    "film_orient": " ".join(map(str, match["film_miller"])),
                    "area": match["match_area"],
                }
                if "elastic_energy" in match:
                    db_entry["energy"] = match["elastic_energy"]
                    db_entry["strain"] = match["strain"]

                all_matches.append(db_entry)

        return all_matches

    def update_targets(self, items):
        """
        Inserts the new substrate matches into the substrates collection

        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """

        items = list(filter(None, itertools.chain.from_iterable(items)))

        if len(items) > 0:
            self.logger.info(
                "Updating {} substrate matches".format(len(items)))
            self.substrates.update(
                key=["film_id", "sub_id", "orient"], docs=items)
        else:
            self.logger.info("No items to update")

    def load_substrate_mats(self):
        """
        Loads the substrate structures from the materials collection
        """

        # TODO: Switch this to be able to take a list of structures and match materials
        # Much more usefull if you want to just prescribe ICSD structures for
        # instance
        mats = [self.materials.find_one(properties=["structure", self.materials.key, self.materials.lu_key], criteria={
                                        self.materials.key: mpid}) for mpid in self.__settings]
        self.substrate_mats = list(filter(None, mats))

    def get_mats_w_updated_elastic_tensors(self):
        e_tensor_updated_mats = []
        self.logger.info("Checking for new/updated elastic tensors")
        if self.elasticity:
            # Find all materials with updated elastic tensors since the
            # substrate builder was last run and rerun all substrates for
            # analysis
            q = self.elasticity.lu_filter(self.substrates)
            e_tensor_updated_mats = self.elasticity.distinct(
                self.elasticity.key, criteria=q)
            # Ensure these materials are within our materials query
            q = dict(self.query)
            q.update({self.materials.key: {"$in": e_tensor_updated_mats}})
            e_tensor_updated_mats = self.materials.distinct(
                self.materials.key, criteria=q)
            self.logger.info(
                "Found {} new/updated elastic tensors".format(len(e_tensor_updated_mats)))

        return e_tensor_updated_mats

    def get_updated_mats(self):
        self.logger.info("Checking for new/updated materials")
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.substrates))
        updated_mats = list(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} new materials for substrate processing".format(len(updated_mats)))
        return updated_mats

    def get_updated_substrates(self):
        # TODO: How do we want to do this?
        self.logger.info("Checking for new/updated substrates")
        for s in self.substrate_mats:
            pass
        return []

    def yield_mats(self, mats, substrates):
        for m in mats:
            e_tensor = self.elasticity.find_one(
                criteria={self.elasticity.key: m})
            mat = self.materials.find_one(
                props=["structure", self.materials.key], criteria={self.materials.key: m})
            yield {"material": mat,
                   "elastic_tensor": e_tensor,
                   "substrates": substrates}


def conventional_standard_structure(doc):
    """Get a conventional standard structure from doc["structure"]."""
    s = Structure.from_dict(doc["structure"])
    spga = SpacegroupAnalyzer(s, symprec=0.1)
    return spga.get_conventional_standard_structure()


def groupby_itemkey(iterable, item):
    """groupby keyed on (and pre-sorted by) itemgetter(item)."""
    itemkey = itemgetter(item)
    return itertools.groupby(sorted(iterable, key=itemkey), itemkey)
