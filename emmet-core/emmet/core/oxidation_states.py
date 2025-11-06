from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Specie

from emmet.core.material_property import PropertyDoc
from emmet.core.types.enums import ValueEnum
from emmet.core.types.pymatgen_types.structure_adapter import StructureType

if TYPE_CHECKING:
    from emmet.core.types.typing import IdentifierType


class OxiStateAssigner(ValueEnum):

    MANUAL = "Manual"
    BVA = "Bond Valence Analysis"
    GUESS = "Oxidation State Guess"


class OxidationStateDoc(PropertyDoc):
    """Oxidation states computed from the structure"""

    property_name: str = "oxidation"

    structure: StructureType = Field(
        ...,
        description="The structure used in the generation of the oxidation state data.",
    )
    possible_species: list[str] = Field(
        description="Possible charged species in this material."
    )
    possible_valences: list[float] = Field(
        description="List of valences for each site in this material."
    )
    average_oxidation_states: dict[str, float] = Field(
        description="Average oxidation states for each unique species."
    )
    method: OxiStateAssigner | None = Field(
        None, description="Method used to compute oxidation states."
    )

    @classmethod
    def from_structure(
        cls, structure: Structure, material_id: IdentifierType | None = None, **kwargs
    ):

        # Check if structure already has oxidation states,
        # if so pass this along unchanged with "method" == "manualx"
        struct_valences: list[float | None] = []
        species = []

        method = None
        if _method := kwargs.pop("method", None):
            method = _method.lower()

        site_oxidation_list = defaultdict(list)
        for site in structure:
            if (oxi_state := getattr(site.species, "oxi_state", None)) and hasattr(
                site.species, "element"
            ):
                site_oxidation_list[site.species.element].append(oxi_state)
                species.append(site.species)
            struct_valences.append(oxi_state)

        average_oxidation_states: dict[str, float] = {
            str(el): np.mean(oxi_states)
            for el, oxi_states in site_oxidation_list.items()
        }

        if any(struct_valences) and (not method):
            d = {
                "possible_species": species,
                "possible_valences": struct_valences,
                "average_oxidation_states": average_oxidation_states,
                "method": OxiStateAssigner.MANUAL,
                "state": "successful",
            }
            return super().from_structure(
                meta_structure=structure, material_id=material_id, **d, **kwargs
            )

        # otherwise, continue with assignment

        structure.remove_oxidation_states()

        # Null document
        d = {
            "possible_species": [],
            "possible_valences": [],
            "average_oxidation_states": {},
            "method": method or OxiStateAssigner.BVA,
            "material_id": material_id,
        }

        if d["method"] == OxiStateAssigner.BVA:
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
                    site_oxidation_list[site.specie.element].append(
                        site.specie.oxi_state
                    )

                oxi_state_dict = {
                    str(el): np.mean(oxi_states) for el, oxi_states in site_oxidation_list.items()  # type: ignore
                }

                d.update(
                    possible_species=list(possible_species),
                    possible_valences=valences,
                    average_oxidation_states=oxi_state_dict,
                )

            except Exception:
                logging.debug(
                    f"BVAnalyzer failed for {structure.composition.reduced_composition}. Trying oxi_state_guesses."
                )
                d["method"] = OxiStateAssigner.GUESS

        if d["method"] == OxiStateAssigner.GUESS:
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

                d.update(
                    possible_species=list(possible_species),
                    possible_valences=valences,
                    average_oxidation_states=first_oxi_state_guess,
                )

            except Exception as e:
                logging.error("Oxidation state guess failed with: {}".format(e))
                d["warnings"] = ["Oxidation state guessing failed."]
                d["state"] = "unsuccessful"
                d["method"] = None

        return super().from_structure(
            meta_structure=structure,
            **d,
            **kwargs,
        )
