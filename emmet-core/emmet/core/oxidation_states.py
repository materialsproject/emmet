import logging
from itertools import groupby
from typing import Dict, List, Literal

import numpy as np
from pydantic import BaseModel
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Specie


class OxidationStateDoc(BaseModel):

    possible_species: List[str]
    possible_valences: List[float]
    average_oxidation_states: Dict[str, float]
    method: Literal["BVAnalyzer", "oxi_state_guesses"]
    structure: Structure

    @classmethod
    def from_structure(cls, structure: Structure):
        structure.remove_oxidation_states()
        try:
            bva = BVAnalyzer()
            valences = bva.get_valences(structure)
            possible_species = {
                str(Specie(structure[idx].specie, oxidation_state=valence))
                for idx, valence in enumerate(valences)
            }

            structure.add_oxidation_state_by_site(valences)

            # construct a dict of average oxi_states for use
            # by MP2020 corrections. The format should mirror
            # the output of the first element from Composition.oxi_state_guesses()
            # e.g. {'Li': 1.0, 'O': -2.0}
            s_list = [(t.specie.element, t.specie.oxi_state) for t in structure.sites]
            s_list = sorted(s_list, key=lambda x: x[0])
            oxi_state_dict = {}
            for c, g in groupby(s_list, key=lambda x: x[0]):
                oxi_state_dict[str(c)] = np.mean([e[1] for e in g])

            d = {
                "possible_species": list(possible_species),
                "possible_valences": valences,
                "average_oxidation_states": oxi_state_dict,
                "method": "BVAnalyzer",
                "structure": structure,
            }

            return cls(**d)

        except Exception as e:
            logging.error("BVAnalyzer failed with: {}".format(e))

            try:
                first_oxi_state_guess = structure.composition.oxi_state_guesses(
                    max_sites=-50
                )[0]
                valences = [
                    first_oxi_state_guess[site.species_string] for site in structure
                ]
                possible_species = {
                    str(Specie(el, oxidation_state=valence))
                    for el, valence in first_oxi_state_guess.items()
                }

                structure.add_oxidation_state_by_site(valences)

                d = {
                    "possible_species": list(possible_species),
                    "possible_valences": valences,
                    "average_oxidation_states": first_oxi_state_guess,
                    "method": "oxi_state_guesses",
                    "structure": structure,
                }

                return cls(**d)

            except Exception as e:
                logging.error("Oxidation state guess failed with: {}".format(e))
