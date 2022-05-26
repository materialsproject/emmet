""" Core definition of document describing molecular chemical reactions """
from typing import Any, Dict, List, Mapping, Tuple, Union

from pydantic import Field

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender

from emmet.core.mpid import MPID
from emmet.core.settings import EmmetSettings
from emmet.core.structure import MoleculeMetadata
from emmet.core.jaguar.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.jaguar.task import TaskDocument, filter_task_type
from emmet.core.jaguar.pes import evaluate_lot, PESMinimumDoc, TransitionStateDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetSettings()

metals = ["Li", "Mg", "Ca", "Zn", "Al"]


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

    sp_end1 = filter_task_type(endpoint1.entries, TaskType.Single_Point)
    sp_end2 = filter_task_type(endpoint2.entries, TaskType.Single_Point)
    sp_ts = filter_task_type(transition_state.entries, TaskType.Single_Point)

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

def bonds_metal_nometal(mg: MoleculeGraph):
    """
    Extract the bonds (with and without counting metal coordination) from a
    MoleculeGraph.

    TODO: Should this functionality just be in pymatgen?

    :param mg: MoleculeGraph
    :return:
        - bonds: List of tuples (a, b) representing bonds, where a and b are
            the 0-based atom indices
        - bonds_nometal: List of tuples (a, b) representing non-coordinate
            bonds, where a and b are the 0-based atom indices
    """

    bonds = list()
    for bond in mg.graph.edges():
        bonds.append(tuple(sorted([bond[0], bond[1]])))

    m_inds = [e for e in range(len(mg.molecule)) if str(mg.molecule.species[e]) in metals]

    bonds_nometal = list()
    for bond in bonds:
        if not any([m in bond for m in m_inds]):
            bonds_nometal.append(bond)

    return (bonds, bonds_nometal)


def bond_species (
        mol: Molecule,
        bond: Tuple[int, int]
):
    """
    Get the elements involved in a bond
    :param mol: Molecule
    :param bond: Tuple (a, b), where a and b are 0-based atom indices representing
        the atoms in the given bond
    :return:
    """

    return "-".join(sorted([str(mol.species[bond[0]]), str(mol.species[bond[1]])]))


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
    transition_state_structure: Molecule = Field(
        None,
        description="Molecule object describing the transition-state of this reaction.",
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
    bond_types_broken: List[str] = Field(
        [],
        description="List of types of bonds being broken during the reaction, e.g. C-O for a "
                    "carbon-oxygen bond."
    )
    bonds_broken_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds broken during the reaction in the form (a, b), where a and b are"
        "0-indexed atom indices, with all metal ions removed.",
    )
    bond_types_broken_nometal: List[str] = Field(
        [],
        description="List of types of bonds being broken during the reaction, e.g. C-O for a "
                    "carbon-oxygen bond. This excludes bonds involving metal ions."
    )
    bonds_formed: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds formed during the reaction in the form (a, b), where a and b are"
        "0-indexed atom indices",
    )
    bond_types_formed: List[str] = Field(
        [],
        description="List of types of bonds being formed during the reaction, e.g. C-O for a "
                    "carbon-oxygen bond."
    )
    bonds_formed_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds formed during the reaction in the form (a, b), where a and b are"
        "0-indexed atom indices, with all metal ions removed",
    )
    bond_types_formed_nometal: List[str] = Field(
        [],
        description="List of types of bonds being formed during the reaction, e.g. C-O for a "
                    "carbon-oxygen bond. This excludes bonds involving metal ions."
    )

    similar_reactions: List[MPID] = Field(
        None,
        description="Reactions that are similar to this one (for instance, because the same types "
                    "of bonds are broken or formed)"
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

        end1_best = endpoint1.best_entries[chosen_lot_opt]
        end2_best = endpoint2.best_entries[chosen_lot_opt]
        ts_best = transition_state.best_entries[chosen_lot_opt]

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
                endpoint1.entries,
                TaskType.Single_Point,
                sort_by=lambda x: (x["level_of_theory"] != chosen_lot_sp, x["energy"]),
            )
            end2_sp = filter_task_type(
                endpoint2.entries,
                TaskType.Single_Point,
                sort_by=lambda x: (x["level_of_theory"] != chosen_lot_sp, x["energy"]),
            )
            ts_sp = filter_task_type(
                transition_state.entries,
                TaskType.Single_Point,
                sort_by=lambda x: (x["level_of_theory"] != chosen_lot_sp, x["energy"]),
            )

            end1_e = end1_sp["energy"] * 27.2114
            end2_e = end2_sp["energy"] * 27.2114
            ts_e = ts_sp["energy"] * 27.2114
        else:
            end1_e = end1_best["energy"] * 27.2114
            end2_e = end2_best["energy"] * 27.2114
            ts_e = ts_best["energy"] * 27.2114

        # TS thermo and structural information
        ts_id = transition_state.molecule_id
        ts_structure = transition_state.molecule
        ts_zpe = ts_best["output"]["zero_point_energy"] * 0.043363

        ts_h = None
        ts_s = None
        ts_g = None
        for thermo in ts_best["output"]["thermo"]:
            if thermo["temperature"] == 298.15:
                ts_h = thermo["enthalpy"]["total_enthalpy"] * 0.043363
                ts_s = thermo["entropy"]["total_entropy"] * 0.000043363
                ts_g = ts_e + ts_zpe + ts_h - 298.15 * ts_s
                break

        # Endpoint thermo and structural information
        # endpoint_1 is the reactant
        if end1_e > end2_e:
            rct_id = endpoint1.molecule_id
            rct_structure = endpoint1.molecule
            rct_e = end1_e
            rct_best = end1_best

            pro_id = endpoint2.molecule_id
            pro_structure = endpoint2.molecule
            pro_e = end2_e
            pro_best = end2_best
        # endpoint_2 is the reactant
        else:
            rct_id = endpoint2.molecule_id
            rct_structure = endpoint2.molecule
            rct_e = end2_e
            rct_best = end2_best

            pro_id = endpoint1.molecule_id
            pro_structure = endpoint1.molecule
            pro_e = end1_e
            pro_best = end1_best

        # Get thermo (at 298.15K, where relevant)
        rct_zpe = rct_best["output"]["zero_point_energy"] * 0.043363
        rct_h = None
        rct_s = None
        rct_g = None
        for thermo in rct_best["output"]["thermo"]:
            if thermo["temperature"] == 298.15:
                rct_h = thermo["enthalpy"]["total_enthalpy"] * 0.043363
                rct_s = thermo["entropy"]["total_entropy"] * 0.000043363
                rct_g = rct_e + rct_zpe + rct_h - 298.15 * rct_s
                break

        pro_zpe = pro_best["output"]["zero_point_energy"] * 0.043363
        pro_h = None
        pro_s = None
        pro_g = None
        for thermo in pro_best["output"]["thermo"]:
            if thermo["temperature"] == 298.15:
                pro_h = thermo["enthalpy"]["total_enthalpy"] * 0.043363
                pro_s = thermo["entropy"]["total_entropy"] * 0.000043363
                pro_g = pro_e + pro_zpe + pro_h - 298.15 * pro_s
                break

        dE = pro_e - rct_e
        dE_barrier = ts_e - rct_e

        try:
            rct_H = rct_e + rct_zpe + rct_h
            ts_H = ts_e + ts_zpe + ts_h
            pro_H = pro_e + pro_zpe + pro_h

            dH = pro_H - rct_H
            dH_barrier = ts_H - rct_H

            dS = pro_s - rct_s
            dS_barrier = ts_s - rct_s

            dG = pro_g - rct_g
            dG_barrier = ts_g - rct_g
        except TypeError:
            dH = None
            dH_barrier = None
            dS = None
            dS_barrier = None
            dG = None
            dG_barrier = None

        # Bonding information
        rct_mg = metal_edge_extender(MoleculeGraph.with_local_env_strategy(rct_structure, OpenBabelNN()))
        rct_bonds, rct_bonds_nometal = bonds_metal_nometal(rct_mg)

        pro_mg = metal_edge_extender(MoleculeGraph.with_local_env_strategy(pro_structure, OpenBabelNN()))
        pro_bonds, pro_bonds_nometal = bonds_metal_nometal(pro_mg)

        #  Use set differences to identify which bonds are not present in rct/pro
        rct_bond_set = set(rct_bonds)
        rct_bond_nometal_set = set(rct_bonds_nometal)
        pro_bond_set = set(pro_bonds)
        pro_bond_nometal_set = set(pro_bonds_nometal)

        bonds_formed = list(pro_bond_set - rct_bond_set)
        bonds_broken = list(rct_bond_set - pro_bond_set)
        bonds_formed_nometal = list(pro_bond_nometal_set - rct_bond_nometal_set)
        bonds_broken_nometal = list(rct_bond_nometal_set - pro_bond_nometal_set)

        # Get bond types, as in C-O or Li-F
        bond_types_formed = list(set(map(lambda x: bond_species(ts_structure, x), bonds_formed)))
        bond_types_broken = list(set(map(lambda x: bond_species(ts_structure, x), bonds_broken)))
        bond_types_formed_nometal = list(set(map(lambda x: bond_species(ts_structure, x), bonds_formed_nometal)))
        bond_types_broken_nometal = list(set(map(lambda x: bond_species(ts_structure, x), bonds_broken_nometal)))

        reaction_id = "-".join([str(rct_id), str(ts_id), str(pro_id)])

        return cls.from_molecule(
            meta_molecule=ts_structure,
            deprecated=deprecated,
            reaction_id=reaction_id,
            reactant_id=rct_id,
            product_id=pro_id,
            transition_state_id=ts_id,
            reactant_structure=rct_structure,
            reactant_molecule_graph=rct_mg,
            reactant_bonds=rct_bonds,
            reactant_bonds_nometal=rct_bonds_nometal,
            reactant_energy=rct_e,
            reactant_zpe=rct_zpe,
            reactant_enthalpy=rct_h,
            reactant_entropy=rct_s,
            reactant_free_energy=rct_g,
            product_structure=pro_structure,
            product_molecule_graph=pro_mg,
            product_bonds=pro_bonds,
            product_bonds_nometal=pro_bonds_nometal,
            product_energy=pro_e,
            product_zpe=pro_zpe,
            product_enthalpy=pro_h,
            product_entropy=pro_s,
            product_free_energy=pro_g,
            transition_state_structure=ts_structure,
            transition_state_energy=ts_e,
            transition_state_zpe=ts_zpe,
            transition_state_enthalpy=ts_h,
            transition_state_entropy=ts_s,
            transition_state_free_energy=ts_g,
            dE=dE,
            dE_barrier=dE_barrier,
            dH=dH,
            dH_barrier=dH_barrier,
            dS=dS,
            dS_barrier=dS_barrier,
            dG=dG,
            dG_barrier=dG_barrier,
            bonds_broken=bonds_broken,
            bond_types_broken=bond_types_broken,
            bonds_broken_nometal=bonds_broken_nometal,
            bond_types_broken_nometal=bond_types_broken_nometal,
            bonds_formed=bonds_formed,
            bond_types_formed=bond_types_formed,
            bonds_formed_nometal=bonds_formed_nometal,
            bond_types_formed_nometal=bond_types_formed_nometal,
            **kwargs
        )