""" Core definition for chemical reactions """

from typing import (
    List,
    Dict,
)

from pydantic import BaseModel, Field
from emmet.stubs import Molecule
from emmet.core.utils import ValueEnum


# TODO: Where are transition states, vertical IP/EA calculations are going to factor into this?


class ReactionType(ValueEnum):
    """
    Type of reaction
    """

    ONE_BOND = "Cleavage or formation of one bond"
    REDOX = "One-electron reduction or oxidation"
    CONCERTED_BONDS = "Concerted mechanism; multiple bonds cleaving or forming"
    DISSOC_REDOX = "Dissociative reduction or oxidation"


class Reaction(BaseModel):
    """
    Basic skeleton structure for a chemical reaction
    """

    reactants: List[Molecule] = Field(..., description="Reactant molecules")

    products: List[Molecule] = Field(..., description="Reactant molecules")

    energy: float = Field(..., description="Reaction energy change in eV")

    enthalpy: float = Field(None, description="Reaction enthalpy change in eV")

    entropy: float = Field(None, description="Reaction entropy change in eV/K")

    reactants_atom_mapping: List[Dict[int, int]] = Field(
        None,
        description="A list of atom mapping number dicts, each dict for one"
        "reactant with the style {atom_index: atom_mapping_number}",
    )

    products_atom_mapping: List[Dict[int, int]] = Field(
        None,
        description="A list of atom mapping number dicts, each dict for one reactant"
        "with the style {atom_index: atom_mapping_number}",
    )

    def free_energy(self, temperature=298.15):
        if self.enthalpy is not None and self.entropy is not None:
            return self.energy + self.enthalpy - temperature * self.entropy
        else:
            raise ValueError("Enthalpy and entropy must be defined for free_energy to be used!")
