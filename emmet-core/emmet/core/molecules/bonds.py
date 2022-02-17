import logging
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple, Union
import copy

from typing_extensions import Literal

import numpy as np
from pydantic import Field
import networkx as nx

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender

from pymatgen.core.periodic_table import Specie, Element

from emmet.core.mpid import MPID
from emmet.core.qchem.task import TaskDocument
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


metals = ["Li", "Mg", "Ca", "Zn", "Al"]


def fix_C_Li_bonds(critic: Dict) -> Dict:
    """
    Adjust C-Li coordinate bonding for Critic2 calculations.

    :param critic: Critic2 output dictionary

    :return:
        critic: modified Critic2 output dictionary

    """
    for key in critic["bonding"]:
        if critic["bonding"][key]["atoms"] == ["Li","C"] or critic["bonding"][key]["atoms"] == ["C","Li"]:
            if critic["bonding"][key]["field"] <= 0.02 and critic["bonding"][key]["field"] > 0.012 and critic["bonding"][key]["distance"] < 2.5:
                critic["processed"]["bonds"].append([int(entry) - 1 for entry in critic["bonding"][key]["atom_ids"]])
    return critic


def make_mol_graph(mol: Molecule, critic_bonds:Optional[List[List[int]]]=None) -> MoleculeGraph:
    """
    Construct a MoleculeGraph using OpenBabelNN with metal_edge_extender and
    (optionally) Critic2 bonding information.

    This bonding scheme was used to define bonding for the Lithium-Ion Battery
    Electrolyte (LIBE) dataset (DOI: 10.1038/s41597-021-00986-9)

    :param mol: Molecule to be converted to MoleculeGraph
    :param critic_bonds: (optional) List of lists [a, b], where a and b are
        atom indices (0-indexed)

    :return: mol_graph, a MoleculeGraph
    """
    mol_graph = MoleculeGraph.with_local_env_strategy(mol,
                                                      OpenBabelNN())
    mol_graph = metal_edge_extender(mol_graph)
    if critic_bonds:
        mg_edges = mol_graph.graph.edges()
        for bond in critic_bonds:
            bond.sort()
            if bond[0] != bond[1]:
                bond = (bond[0], bond[1])
                if bond not in mg_edges:
                    mol_graph.add_edge(bond[0],bond[1])
    return mol_graph


def nbo_molecule_graph(
        mol: Molecule,
        nbo: Dict[str, Any]
):
    """
    Construct a molecule graph from NBO data.

    :param mol: molecule to be analyzed
    :param nbo: Output from NBO7
    :return:
    """

    mg = MoleculeGraph.with_empty_graph(mol)

    warnings = set()

    alpha_bonds = set()
    beta_bonds = set()

    if len(nbo["hybridization_character"]) >= 2:
        for bond_ind in nbo["hybridization_character"][1].get("type", list()):
            if nbo["hybridization_character"][1]["type"][bond_ind] != "BD":
                continue

            from_ind = int(nbo["hybridization_character"][1]["atom 1 number"][bond_ind]) - 1
            to_ind = int(nbo["hybridization_character"][1]["atom 2 number"][bond_ind]) - 1

            if nbo["hybridization_character"][1]["atom 1 symbol"][bond_ind] in metals:
                m_contrib = float(nbo["hybridization_character"][1]["atom 1 polarization"][bond_ind])
            elif nbo["hybridization_character"][1]["atom 2 symbol"][bond_ind] in metals:
                m_contrib = float(nbo["hybridization_character"][1]["atom 2 polarization"][bond_ind])
            else:
                m_contrib = None

            if m_contrib is None or m_contrib >= 30.0:
                bond_type = "covalent"
                warnings.add("Contains covalent bond with metal atom")
            else:
                bond_type = "electrostatic"

            alpha_bonds.add((from_ind, to_ind, bond_type))

    if mol.spin_multiplicity != 1 and len(nbo["hybridization_character"]) >= 4:
        for bond_ind in nbo["hybridization_character"][3].get("type", list()):
            if nbo["hybridization_character"][3]["type"][bond_ind] != "BD":
                continue

            from_ind = int(nbo["hybridization_character"][3]["atom 1 number"][bond_ind]) - 1
            to_ind = int(nbo["hybridization_character"][3]["atom 2 number"][bond_ind]) - 1

            if nbo["hybridization_character"][3]["atom 1 symbol"][bond_ind] in metals:
                m_contrib = float(nbo["hybridization_character"][3]["atom 1 polarization"][bond_ind])
            elif nbo["hybridization_character"][3]["atom 2 symbol"][bond_ind] in metals:
                m_contrib = float(nbo["hybridization_character"][3]["atom 2 polarization"][bond_ind])
            else:
                m_contrib = None

            if m_contrib is None or m_contrib >= 30.0:
                bond_type = "covalent"
                warnings.add("Contains covalent bond with metal atom")
            else:
                bond_type = "electrostatic"

            beta_bonds.add((from_ind, to_ind, bond_type))

    distance_cutoff = 3.0
    energy_cutoff = 3.0
    metal_indices = [i for i, e in enumerate(mol.species) if e in metals]

    poss_coord = dict()
    dist_mat = mol.distance_matrix
    for i in metal_indices:
        poss_coord[i] = list()
        row = dist_mat[i]
        for j, val in enumerate(row):
            if i != j and val < distance_cutoff:
                poss_coord[i].append(j)

    if len(nbo["perturbation_energy"]) > 0:
        for inter_ind in nbo["perturbation_energy"][0].get("donor type", list()):
            coord = False
            m_ind = None
            x_ind = None
            if int(nbo["perturbation_energy"][0]["acceptor atom 1 number"][inter_ind]) - 1 in metal_indices:
                if nbo["perturbation_energy"][0]["donor type"][inter_ind] == "LP" and nbo["perturbation_energy"][0]["acceptor type"][inter_ind] == "LV":
                    coord = True
                    m_ind = int(nbo["perturbation_energy"][0]["acceptor atom 1 number"][inter_ind]) - 1
                    x_ind = int(nbo["perturbation_energy"][0]["donor atom 1 number"][inter_ind]) - 1
                elif nbo["perturbation_energy"][0]["donor type"][inter_ind] == "LP" and nbo["perturbation_energy"][0]["acceptor type"][inter_ind] == "RY*":
                    coord = True
                    m_ind = int(nbo["perturbation_energy"][0]["acceptor atom 1 number"][inter_ind]) - 1
                    x_ind = int(nbo["perturbation_energy"][0]["donor atom 1 number"][inter_ind]) - 1
            elif nbo["perturbation_energy"][0]["donor atom 1 number"][inter_ind] - 1 in metal_indices:
                if nbo["perturbation_energy"][0]["donor type"][inter_ind] == "LP" and nbo["perturbation_energy"][0]["acceptor type"][inter_ind] == "LV":
                    coord = True
                    m_ind = int(nbo["perturbation_energy"][0]["donor atom 1 number"][inter_ind]) - 1
                    x_ind = int(nbo["perturbation_energy"][0]["acceptor atom 1 number"][inter_ind]) - 1

            if not coord:
                continue
            elif x_ind not in poss_coord[m_ind]:
                continue

            energy = float(nbo["perturbation_energy"][0]["perturbation energy"][inter_ind])
            if energy >= energy_cutoff:
                alpha_bonds.add((x_ind, m_ind, "electrostatic"))

    if mol.spin_multiplicity != 1 and len(nbo["perturbation_energy"]) > 1:
        for inter_ind in nbo["perturbation_energy"][1].get("donor type", list()):
            coord = False
            m_ind = None
            x_ind = None
            if nbo["perturbation_energy"][1]["acceptor atom 1 number"][inter_ind] - 1 in metal_indices:
                if nbo["perturbation_energy"][1]["donor type"][inter_ind] == "LP" and nbo["perturbation_energy"][1]["acceptor type"][inter_ind] == "LV":
                    coord = True
                    m_ind = int(nbo["perturbation_energy"][1]["acceptor atom 1 number"][inter_ind]) - 1
                    x_ind = int(nbo["perturbation_energy"][1]["donor atom 1 number"][inter_ind]) - 1
                elif nbo["perturbation_energy"][1]["donor type"][inter_ind] == "LP" and nbo["perturbation_energy"][1]["acceptor type"][inter_ind] == "RY*":
                    coord = True
                    m_ind = int(nbo["perturbation_energy"][1]["acceptor atom 1 number"][inter_ind]) - 1
                    x_ind = int(nbo["perturbation_energy"][1]["donor atom 1 number"][inter_ind]) - 1
            elif nbo["perturbation_energy"][1]["donor atom 1 number"][inter_ind] - 1 in metal_indices:
                if nbo["perturbation_energy"][1]["donor type"][inter_ind] == "LP" and nbo["perturbation_energy"][1]["acceptor type"][inter_ind] == "LV":
                    coord = True
                    m_ind = int(nbo["perturbation_energy"][1]["donor atom 1 number"][inter_ind]) - 1
                    x_ind = int(nbo["perturbation_energy"][1]["acceptor atom 1 number"][inter_ind]) - 1

            if not coord:
                continue
            elif x_ind not in poss_coord[m_ind]:
                continue

            energy = float(nbo["perturbation_energy"][1]["perturbation energy"][inter_ind])
            if energy >= energy_cutoff:
                beta_bonds.add((x_ind, m_ind, "electrostatic"))

    sorted_alpha = set([tuple(sorted([a[0], a[1]])) for a in alpha_bonds])
    sorted_beta = set([tuple(sorted([b[0], b[1]])) for b in beta_bonds])

    if sorted_alpha != sorted_beta:
        warnings.add("Difference in bonding between alpha and beta electrons")

    for bond in alpha_bonds.union(beta_bonds):
        if (bond[0], bond[1]) not in mg.graph.edges() and (bond[1], bond[0]) not in mg.graph.edges():
            if bond[0] < bond[1]:
                mg.add_edge(bond[0], bond[1], edge_properties={"type": bond[2]})
            else:
                mg.add_edge(bond[1], bond[0], edge_properties={"type": bond[2]})

    mg_copy = copy.deepcopy(mg)
    mg_copy.remove_nodes(metal_indices)

    if not nx.is_connected(mg_copy.graph.to_undirected()):
        warnings.add("Metal-centered complex")

    return (mg, list(warnings))


class BondingDoc(PropertyDoc):
    """Representation of molecular bonding."""

    property_name = "bonding"

    molecule_graph: MoleculeGraph = Field(..., description="Molecule graph")

    method: str = Field(..., description="Method used to compute molecule graph")

    bond_types: Dict[str, List[float]] = Field(
        dict(),
        description="Dictionary of bond types to their length, e.g. C-O to "
        "a list of the lengths of C-O bonds in Angstrom."
    )

    bonds: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds in the form (a, b), where a and b are 0-indexed atom indices",
    )

    bonds_nometal: List[Tuple[int, int]] = Field(
        [],
        description="List of bonds in the form (a, b), where a and b are 0-indexed atom indices, "
                    "with all metal ions removed",
    )

    @classmethod
    def from_task(
        cls,
        task: TaskDocument,
        molecule_id: MPID,
        deprecated: bool=False,
        preferred_methods: Tuple = ("NBO7", "Critic2", "OpenBabelNN + metal_edge_extender"),
        **kwargs
    ): # type: ignore[override]
        """
        Determine bonding from a task document

        Method preferences are as follows:
        - NBO7
        - OpenBabelNN + metal_edge_extender in pymatgen
        - Critic2 (really OpenBabelNN + metal_edge_extender + Critic2)

        :param task: task document from which bonding properties can be extracted
        :param molecule_id: mpid
        :param preferred_methods: list of methods; by default, NBO7, Critic2, and the combination
            of OpenBabelNN and metal_edge_extender in pymatgen, in that order
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        mg = None
        method = None
        warnings = list()

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        for m in preferred_methods:
            if mg is not None:
                break

            if m == "NBO7" and task.output.nbo is not None:
                if task.orig["rem"].get("run_nbo6", False):
                    method = "NBO7"
                    mg, warnings = nbo_molecule_graph(mol, task.output.nbo)

            elif m == "Critic2" and task.critic2 is not None:
                method = "Critic2"
                critic = fix_C_Li_bonds(task.critic2)
                critic_bonds = critic["processed"]["bonds"]
                mg = make_mol_graph(mol, critic_bonds=critic_bonds)

            else:
                method = "OpenBabelNN + metal_edge_extender"
                mg = make_mol_graph(mol)

        bonds = list()
        for bond in mg.graph.edges():
            bonds.append(sorted([bond[0],bond[1]]))

        # Calculate bond lengths
        bond_types = dict()
        for u, v in mg.graph.edges():
            species_u = str(mg.molecule.species[u])
            species_v = str(mg.molecule.species[v])
            if species_u < species_v:
                species = f"{species_u}-{species_v}"
            else:
                species = f"{species_v}-{species_u}"
            dist = mg.molecule.get_distance(u, v)
            if species not in bond_types:
                bond_types[species] = [dist]
            else:
                bond_types[species].append(dist)

        m_inds = [e for e in range(len(mol)) if str(mol.species[e]) in metals]

        bonds_nometal = list()
        for bond in bonds:
            if not any([m in bond for m in m_inds]):
                bonds_nometal.append(bond)

        return super().from_molecule(
            meta_molecule=mol,
            molecule_id=molecule_id,
            method=method,
            warnings=warnings,
            molecule_graph=mg,
            bond_types=bond_types,
            bonds=bonds,
            bonds_nometal=bonds_nometal,
            deprecated=deprecated,
            origins=[PropertyOrigin(name="bonding", task_id=task.task_id)],
            **kwargs
        )