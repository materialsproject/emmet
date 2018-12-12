import os.path
from monty.serialization import loadfn

from pymatgen.core.structure import Structure
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.core.periodic_table import Specie
from pymatgen import __version__ as pymatgen_version

from maggma.builders import MapBuilder
from maggma.validator import JSONSchemaValidator

MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
BOND_VALENCE_SCHEMA = os.path.join(MODULE_DIR, "schema", "bond_valence.json")


class BondValenceBuilder(MapBuilder):
    """
    Calculate plausible oxidation states from structures.
    """

    def __init__(self, materials, bond_valence, **kwargs):

        self.materials = materials
        self.bond_valence = bond_valence
        self.bond_valence.validator = JSONSchemaValidator(loadfn(BOND_VALENCE_SCHEMA))
        super().__init__(source=materials, target=bond_valence, ufn=self.calc, projection=["structure"], **kwargs)

    def calc(self, item):
        s = Structure.from_dict(item['structure'])

        d = {"pymatgen_version": pymatgen_version, "successful": False}

        try:
            bva = BVAnalyzer()
            valences = bva.get_valences(s)
            possible_species = {
                str(Specie(s[idx].specie, oxidation_state=valence))
                for idx, valence in enumerate(valences)
            }

            method = "BVAnalyzer"

            d["successful"] = True
            d["bond_valence"] = {
                "possible_species": list(possible_species),
                "possible_valences": valences,
                "method": "BVAnalyzer"
            }

        except Exception as e:
            self.logger.error("BVAnalyzer failed with: {}".format(e))

            try:
                first_oxi_state_guess = s.composition.oxi_state_guesses()[0]
                valences = [first_oxi_state_guess[site.species_string] for site in s]
                possible_species = {
                    str(Specie(el, oxidation_state=valence))
                    for el, valence in first_oxi_state_guess.items()
                }
                d["successful"] = True
                d["bond_valence"] = {
                    "possible_species": list(possible_species),
                    "possible_valences": valences,
                    "method": "oxi_state_guesses"
                }
            except Exception as e:
                self.logger.error("Oxidation state guess failed with: {}".format(e))

        return d
