from pymatgen.core.structure import Structure
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.core.periodic_table import Specie
from pymatgen import __version__ as pymatgen_version

from maggma.builder import Builder
from maggma.validator import JSONSchemaValidator


BOND_VALENCE_SCHEMA = {
    "title": "bond_valence",
    "type": "object",
    "properties":
        {
            "task_id": {"type": "string"},
            "method": {"type": "string"},
            "possible_species": {"type": "array", "items": {"type": "strinig"}},
            "possible_valences": {"type": "array", "items": {"type": "number"}},
            "successful": {"type": "boolean"},
            "pymatgen_version": {"type": "string"},
        },
    "required": ["task_id", "successful", "pymatgen_version"]
}


class BondValenceBuilder(Builder):
    """
    Calculate plausible oxidation states from structures.
    """

    def __init__(self, materials, bond_valence,
                 query=None, **kwargs):

        self.materials = materials
        self.bond_valence = bond_valence
        self.query = query or {}

        super().__init__(sources=[materials],
                         targets=[bond_valence],
                         **kwargs)

    def get_items(self):

        materials = self.materials.query(criteria=self.query,
                                         properties=["task_id", "structure"])
        # All relevant materials that have been updated since bond valences
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.bond_valence))
        new_keys = list(self.materials.distinct(self.materials.key, q))

        materials = self.materials.query(criteria={self.materials.key: {'$in': new_keys}},
                                         properties=["task_id", "structure"])

        self.total = materials.count()
        self.logger.info("Found {} new materials for bond valence analysis".format(self.total))

        for material in materials:
            yield material

    def process_item(self, item):
        s = Structure.from_dict(item['structure'])
        try:
            bva = BVAnalyzer()
            valences = bva.get_valences(s)
            possible_species = {str(Specie(s[idx].specie, oxidation_state=valence))
                                for idx, valence in enumerate(valences)}

            method = "BVAnalyzer"
        except ValueError:
            try:
                first_oxi_state_guess = s.composition.oxi_state_guesses()[0]
                valences = [first_oxi_state_guess[site.species_string] for site in s]
                possible_species = {str(Specie(el, oxidation_state=valence))
                                    for el, valence in first_oxi_state_guess.items()}
                method = "oxi_state_guesses"
            except:
                return {
                    "task_id": item['task_id'],
                    "pymatgen_version": pymatgen_version,
                    "successful": False
                }

        return {
            "task_id": item['task_id'],
            "possible_species": list(possible_species),
            "possible_valences": valences,
            "method": method,
            "pymatgen_version": pymatgen_version,
            "successful": True
        }

    def update_targets(self, items):
        self.logger.debug("Updating {} bond valence documents".format(len(items)))
        self.bond_valence.update(docs=items, key=['task_id'])
