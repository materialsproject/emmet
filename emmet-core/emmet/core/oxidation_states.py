import logging
from collections import defaultdict
from typing import Dict, List

import numpy as np
from pydantic import Field
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Specie
from typing_extensions import Literal

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID


class OxidationStateDoc(PropertyDoc):
    """Oxidation states computed from the structure"""

    property_name = "oxidation"

    structure: Structure = Field(
        ...,
        description="The structure used in the generation of the oxidation state data",
    )
    possible_species: List[str] = Field(
        description="Possible charged species in this material"
    )
    possible_valences: List[float] = Field(
        description="List of valences for each site in this material"
    )
    average_oxidation_states: Dict[str, float] = Field(
        description="Average oxidation states for each unique species"
    )
    method: str = Field(None, description="Method used to compute oxidation states")

    @classmethod
    def from_structure(cls, structure: Structure, material_id: MPID, **kwargs):  # type: ignore[override]

        # TODO: add check for if it already has oxidation states, if so pass this along unchanged ("method": "manual")
        structure.remove_oxidation_states()

        # Null document
        d = {
            "possible_species": [],
            "possible_valences": [],
            "average_oxidation_states": {},
        }  # type: dict

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
                str(el): np.mean(oxi_states)  # type: ignore
                for el, oxi_states in site_oxidation_list.items()
            }

            d = {
                "possible_species": list(possible_species),
                "possible_valences": valences,
                "average_oxidation_states": oxi_state_dict,
                "method": "Bond Valence Analysis",
            }

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
                    "method": "Oxidation State Guess",
                }

            except Exception as e:
                logging.error("Oxidation state guess failed with: {}".format(e))
                d["warnings"] = ["Oxidation state guessing failed."]
                d["state"] = "unsuccessful"

        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            structure=structure,
            **d,
            **kwargs
        )
