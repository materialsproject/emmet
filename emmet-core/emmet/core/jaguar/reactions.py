""" Core definition of document describing molecular chemical reactions """
from typing import Any, Dict, List, Mapping, Tuple, Union

from pydantic import Field

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph

from emmet.core.mpid import MPID
from emmet.core.settings import EmmetSettings
from emmet.core.structure import MoleculeMetadata
from emmet.core.jaguar.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.jaguar.task import TaskDocument, filter_task_type
from emmet.core.jaguar.pes import evaluate_lot, PESMinimumDoc, TransitionStateDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetSettings()

# Notes:
# - Reactions should be defined in the exergonic direction
#   That is, products should always be lower in (free) energy than reactants


def find_common_reaction_lot_opt(
    endpoint1: PESMinimumDoc,
    endpoint2: PESMinimumDoc,
    transition_state: TransitionStateDoc,
) -> str:
    """
    Identify the highest level of theory (LOT) used in two PESMinimumDocs
    (reaction endpoints) and one TransitionStateDoc for geometry optimization.

    :param endpoint1: PESMinimumDoc for the first endpoint
    :param endpoint2: PESMinimumDoc for the second endpoint
    :param transition_state: TransitionStateDoc for the transition-state of this
        reaction
    :return: String representation of the best common level of theory.
    """
    lots_end1 = sorted(endpoint1.best_entries.keys(), key=lambda x: evaluate_lot(x))
    lots_end2 = sorted(endpoint2.best_entries.keys(), key=lambda x: evaluate_lot(x))
    lots_ts = sorted(
        transition_state.best_entries.keys(), key=lambda x: evaluate_lot(x)
    )

    for lot in lots_ts:
        if lot in lots_end1 and lot in lots_end2:
            return lot

    return None


def find_common_reaction_lot_sp(
    endpoint1: PESMinimumDoc,
    endpoint2: PESMinimumDoc,
    transition_state: TransitionStateDoc,
) -> str:
    """
    Identify the highest level of theory (LOT) used by two PESMinimumDocs
    (reaction endpoints) and one TransitionStateDoc for single-point energy
    evaluations.

    :param endpoint1: PESMinimumDoc for the first endpoint
    :param endpoint2: PESMinimumDoc for the second endpoint
    :param transition_state: TransitionStateDoc for the transition-state of this
        reaction
    :return: String representation of the best common level of theory.
    """

    sp_end1 = filter_task_type(endpoint1["entries"], TaskType.Single_Point)
    sp_end2 = filter_task_type(endpoint2["entries"], TaskType.Single_Point)
    sp_ts = filter_task_type(transition_state["entries"], TaskType.Single_Point)

    lots_end1 = sorted(
        list({e["level_of_theory"] for e in sp_end1}), key=lambda x: evaluate_lot(x)
    )
    lots_end2 = sorted(
        list({e["level_of_theory"] for e in sp_end2}), key=lambda x: evaluate_lot(x)
    )
    lots_ts = sorted(
        list({e["level_of_theory"] for e in sp_ts}), key=lambda x: evaluate_lot(x)
    )
    for lot in lots_ts:
        if lot in lots_end1 and lot in lots_end2:
            return lot

    return None


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
        description="List of bonds in the reactants in the form (a, b), where a and b are 0-indexed "
        "atom indices",
    )
    reactant_bonds_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds in the reactants in the form (a, b), where a and b are 0-indexed "
        "atom indices, with all metal ions removed",
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
        description="List of bonds in the products in the form (a, b), where a and b are 0-indexed "
        "atom indices",
    )
    product_bonds_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds in the products in the form (a, b), where a and b are 0-indexed "
        "atom indices, with all metal ions removed",
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

    # Reaction barrier
    dE_barrier: float = Field(
        None,
        description="Electronic energy barrier (TS - reactant) of this reaction (units: eV).",
    )
    dH_barrier: float = Field(
        None,
        description="Enthalpy barrier (TS - reactant) of this reaction " "(units: eV).",
    )
    dS_barrier: float = Field(
        None,
        description="Entropy barrier (TS - reactant) of this reaction (units: eV/K).",
    )
    dG_barrier: float = Field(
        None, description="Gibbs free energy barrier (TS - reactant) " "(units: eV)."
    )

    # Bonding changes
    bonds_broken: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds broken during the reaction in the form (a, b), where a and b are"
        "0-indexed atom indices.",
    )
    bonds_broken_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds broken during the reaction in the form (a, b), where a and b are"
        "0-indexed atom indices, with all metal ions removed.",
    )
    bonds_formed: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds formed during the reaction in the form (a, b), where a and b are"
        "0-indexed atom indices",
    )
    bonds_formed_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds formed during the reaction in the form (a, b), where a and b are"
        "0-indexed atom indices, with all metal ions removed",
    )

    @classmethod
    def from_docs(
        cls,
        endpoint1: PESMinimumDoc,
        endpoint2: PESMinimumDoc,
        transition_state: TransitionStateDoc,
        deprecated: bool = False,
        **kwargs
    ):  # type: ignore[override]
        """
        Define a reaction based on reactant & product complexes and a
        transition-state

        :param endpoint1: PESMinimumDoc describing one endpoint of this reaction
        :param products: PESMinimumDOc describing the other endpoint of this
            reaction
        :param transition_state: TransitionStateDoc describing the TS of this
            reaction
        :param deprecated: Bool. Is this reaction deprecated?
        :param kwargs:
        :return: ReactionDoc
        """

        # Find best common LevelOfTheory
        # Use that LOT to calculate thermodynamic properties
        # Decide which endpoint is reactant/product based on ∆G
        # Take deltas of everything
        # Extract basic information (IDs, structures)
        # Make MoleculeGraphs

        # Find best level of theory - optimization
        chosen_lot_opt = find_common_reaction_lot_opt(
            endpoint1, endpoint2, transition_state
        )

        if chosen_lot_opt is None:
            raise ValueError(
                "Endpoints and Transition-State have no LevelOfTheory in common! Cannot compare."
            )

        # Find best level of theory - single-point
        chosen_lot_sp = find_common_reaction_lot_sp(
            endpoint1, endpoint2, transition_state
        )

        # If there are high-quality single-points, use them for energy
        if chosen_lot_sp is not None and evaluate_lot(chosen_lot_sp) < evaluate_lot(
            chosen_lot_opt
        ):
            end1_sp = filter_task_type(
                endpoint1["entries"],
                TaskType.Single_Point,
                sort_by=lambda x: (x["level_of_theory"] != chosen_lot_sp, x["energy"]),
            )
            end2_sp = filter_task_type(
                endpoint2["entries"],
                TaskType.Single_Point,
                sort_by=lambda x: (x["level_of_theory"] != chosen_lot_sp, x["energy"]),
            )
            ts_sp = filter_task_type(
                transition_state["entries"],
                TaskType.Single_Point,
                sort_by=lambda x: (x["level_of_theory"] != chosen_lot_sp, x["energy"]),
            )
