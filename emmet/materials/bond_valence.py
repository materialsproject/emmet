from pymatgen.core.structure import Structure
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.core.periodic_table import Specie
from pymatgen import __version__ as pymatgen_version

from maggma.examples.builders import MapBuilder
from maggma.validator import JSONSchemaValidator

BOND_VALENCE_SCHEMA = {
    "title": "bond_valence",
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string"
        },
        "method": {
            "type": "string"
        },
        "possible_species": {
            "type": "array",
            "items": {
                "type": "strinig"
            }
        },
        "possible_valences": {
            "type": "array",
            "items": {
                "type": "number"
            }
        },
        "successful": {
            "type": "boolean"
        },
        "pymatgen_version": {
            "type": "string"
        },
    },
    "required": ["task_id", "successful", "pymatgen_version"]
}


class BondValenceBuilder(MapBuilder):
    """
    Calculate plausible oxidation states from structures.
    """

    def __init__(self, materials, bond_valence, **kwargs):

        self.materials = materials
        self.bond_valence = bond_valence

        super().__init__(source=materials, target=bond_valence, ufn=self.calc, projection=["structure"], **kwargs)

    def calc(self, item):
        s = Structure.from_dict(item['structure'])

        d = {"pymatgen_version": pymatgen_version, "successful": False}

        try:
            bva = BVAnalyzer()
            valences = bva.get_valences(s)
            possible_species = {
                str(Specie(s[idx].specie, oxidation_state=valence)) for idx, valence in enumerate(valences)
            }

            method = "BVAnalyzer"

            d["successful"] = True
            d["method"] = "oxi_state_guesses"
            d["bond_valence"] = {"possible_species": list(possible_species), "possible_valences": valences}

        except ValueError:
            try:
                first_oxi_state_guess = s.composition.oxi_state_guesses()[0]
                valences = [first_oxi_state_guess[site.species_string] for site in s]
                possible_species = {
                    str(Specie(el, oxidation_state=valence)) for el, valence in first_oxi_state_guess.items()
                }
                d["successful"] = True
                d["method"] = "oxi_state_guesses"
                d["bond_valence"] = {"possible_species": list(possible_species), "possible_valences": valences}
            except:
                pass

        return d
