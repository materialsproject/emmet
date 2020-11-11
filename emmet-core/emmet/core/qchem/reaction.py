""" Core definition of Reaction Documents """

from datetime import datetime

from typing import (
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    List,
    Dict,
)

from pydantic import BaseModel, Field
from pymatgen.analysis.graphs import MoleculeGraph
from emmet.stubs import Molecule
from emmet.core.utils import ValueEnum


#TODO: Where are transition states, vertical IP/EA calculations are going to factor into this?


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
        description="A list of atom mapping number dicts, each dict for one reactant with the style {atom_index: atom_mapping_number}"
    )

    products_atom_mapping: List[Dict[int, int]] = Field(
        None,
        description="A list of atom mapping number dicts, each dict for one reactant with the style {atom_index: atom_mapping_number}"
    )

    def free_energy(self, temperature=298.15):
        return self.energy + self.enthalpy - temperature * self.entropy

    # energy_barrier: float = Field(None, description="Reaction energy barrier (TS - reactants) in eV")
    #
    # enthalpy_barrier: float = Field(None, description="Reaction enthalpy barrier (TS - reactants) in eV")
    #
    # entropy_barrier: float = Field(None, description="Reaction entropy barrier (TS - reactants) in eV/K")
    #
    # def free_energy_barrier(self, temperature=298.15):
    #     return self.energy_barrier + self.enthalpy_barrier - temperature * self.entropy_barrier
    #
    # inner_reorganization_energy: float = Field(
    #     None,
    #     description="Inner reorganization energy for Marcus theory redox rate prediction"
    # )
    #
    # outer_reorganization_energy: float = Field(
    #     None,
    #     description="Outer reorganization energy for Marcus theory redox rate prediction"
    # )


class ReactionDoc(BaseModel):
    """
    Definition for a Reaction Document
    """

    reaction_id: str = Field(
        ...,
        description="The ID of this reaction, used as a universal reference across all related Documents."
        "This comes in the form mprxn-*******"
    )

    reaction: Reaction = Field(
        ...,
        description="Reactant/product Molecules along with thermodynamic information for this Reaction."
    )

    reactant_ids: List[str] = Field(..., description="Molecule IDs for each reactant molecule")

    product_ids: List[str] = Field(..., description="Molecule IDs for each product molecule")

    reaction_type: ReactionType = Field(..., description="Type of this reaction")

    deprecated: bool = Field(
        False,
        description="Has this molecule been deprecated?"
    )

    task_ids: Sequence[str] = Field(
        list(),
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Reaction Document",
    )

    calc_types: Mapping[str, str] = Field(
        None,
        description="Calculation types for all the calculations that make up this reaction",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this reaction document was last updated",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this reaction document was first created",
        default_factory=datetime.utcnow,
    )

    warnings: Sequence[str] = Field(
        list(), description="Any warnings related to this reaction"
    )

    sandboxes: Sequence[str] = Field(
        ["core"],
        description="List of sandboxes this reaction belongs to."
        " Sandboxes provide a way of controlling access to reactions."
        " Core is the primary sandbox for fully open documents",
    )
