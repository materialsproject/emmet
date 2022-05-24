""" Core definition of document describing molecular chemical reactions """
from typing import Any, Dict, List, Mapping, Tuple, Union

from pydantic import Field

from pymatgen.core.structure import Molecule
from pymatgen.analysis.molecule_matcher import MoleculeMatcher
from pymatgen.analysis.graphs import MoleculeGraph

from emmet.core.mpid import MPID
from emmet.core.settings import EmmetSettings
from emmet.core.material import MoleculeDoc as CoreMoleculeDoc
from emmet.core.material import PropertyOrigin
from emmet.core.structure import MoleculeMetadata
from emmet.core.jaguar.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.jaguar.task import TaskDocument
from emmet.core.jaguar.pes import PESPointDoc, PESMinimumDoc, TransitionStateDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetSettings()

# Notes:
# - Reactions should be defined in the exergonic direction
#   That is, products should always be lower in (free) energy than reactants
# - TS bonding is poorly defined essentially by its nature
#   But, should PESMinimumDocs have bonding information?


class ReactionDoc(MoleculeMetadata):

    reaction_id: MPID = Field(..., description="Unique identifier for this reaction.")

    reactant_id: MPID = Field(
        ..., description="Unique ID for the reactants for this reaction."
    )
    product_id: MPID = Field(
        ..., description="Unique ID for the products for this reaction."
    )
    transition_state_id: MPID = Field(
        ..., description="Unique ID of the transition-state for this reaction."
    )

    reactant_structure: Molecule = Field(
        None, description="Molecule object describing the reactants of this reaction."
    )
    reactant_molecule_graph: MoleculeGraph = Field(
        None,
        description="Structural and bonding information for the reactants of this reaction.",
    )
    reactant_bonds: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds in the reactants in the form (a, b), where a and b are 0-indexed atom indices",
    )
    reactant_bonds_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds in the reactants in the form (a, b), where a and b are 0-indexed atom indices, "
        "with all metal ions removed",
    )
    reactant_energy: float = Field(
        None,
        description="Electronic energy of the reactants of this reaction (units: eV).",
    )
    reactant_zpe: float = Field(
        None,
        description="Vibrational zero-point energy of the reactants of this reaction (units: eV).",
    )
    reactant_enthalpy: float = Field(
        None, description="Enthalpy of the reactants of this reaction (units: eV)."
    )
    reactant_entropy: float = Field(
        None, description="Entropy of the reactants of this reaction (units: eV/K)."
    )
    reactant_free_energy: float = Field(
        None,
        description="Gibbs free energy of the reactants of this reaction at 298.15K (units: eV).",
    )

    # Product properties
    product_structure: Molecule = Field(
        None, description="Molecule object describing the products of this reaction."
    )
    product_molecule_graph: MoleculeGraph = Field(
        None,
        description="Structural and bonding information for the products of this reaction.",
    )
    product_bonds: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds in the products in the form (a, b), where a and b are 0-indexed atom indices",
    )
    product_bonds_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds in the products in the form (a, b), where a and b are 0-indexed atom indices, "
        "with all metal ions removed",
    )
    product_energy: float = Field(
        None,
        description="Electronic energy of the products of this reaction (units: eV).",
    )
    product_zpe: float = Field(
        None,
        description="Vibrational zero-point energy of the products of this reaction (units: eV).",
    )
    product_enthalpy: float = Field(
        None, description="Enthalpy of the products of this reaction (units: eV)."
    )
    product_entropy: float = Field(
        None, description="Entropy of the products of this reaction (units: eV/K)."
    )
    product_free_energy: float = Field(
        None,
        description="Gibbs free energy of the products of this reaction at 298.15K (units: eV).",
    )

    # TS properties
    transition_state_structures: List[Molecule] = Field(
        None,
        description="Molecule objects describing the transition_states of this reaction.",
    )
    transition_state_energy: float = Field(
        None,
        description="Electronic energy of the transition_states of this reaction (units: eV).",
    )
    transition_state_zpe: float = Field(
        None,
        description="Vibrational zero-point energy of the transition_states of this reaction (units: eV).",
    )
    transition_state_enthalpy: float = Field(
        None,
        description="Enthalpy of the transition_states of this reaction (units: eV).",
    )
    transition_state_entropy: float = Field(
        None,
        description="Entropy of the transition_states of this reaction (units: eV/K).",
    )
    transition_state_free_energy: float = Field(
        None,
        description="Gibbs free energy of the transition_states of this reaction at 298.15K (units: eV).",
    )

    # Reaction thermodynamics
    dE: float = Field(
        None, description="Electronic energy change of this reaction (units: eV)."
    )
    dH: float = Field(None, description="Enthalpy change of this reaction (units: eV).")
    dS: float = Field(
        None, description="Entropy change of this reaction (units: eV/K)."
    )
    dG: float = Field(None, description="Gibbs free energy (units: eV).")

    @classmethod
    def from_docs(
        cls,
        reactants: PESMinimumDoc,
        products: PESMinimumDoc,
        transition_state: TransitionStateDoc,
        deprecated: bool = False,
        **kwargs
    ):  # type: ignore[override]
        # Extract basic information (IDs, structures)
        # Make MoleculeGraphs
        # Find best common LevelOfTheory
        # Use that LOT to calculate thermodynamic properties
        # Take deltas of everything
        pass
