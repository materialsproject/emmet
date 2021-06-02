import logging
from collections import defaultdict
from typing import Dict, List

import numpy as np
from pydantic import BaseModel
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Specie
from typing_extensions import Literal


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

            site_oxidation_list = defaultdict(list)
            for site in structure:
                site_oxidation_list[site.specie.element].append(site.specie.oxi_state)

            oxi_state_dict = {
                str(el): np.mean(oxi_states)
                for el, oxi_states in site_oxidation_list.items()
            }

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
                raise e
