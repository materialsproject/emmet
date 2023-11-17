from typing import Dict, List, Any, Optional, Tuple
import copy
from hashlib import blake2b

from pydantic import Field
import networkx as nx

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph

from emmet.core.mpid import MPculeID
from emmet.core.utils import make_mol_graph
from emmet.core.qchem.task import TaskDocument
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


metals = [
    "Li",
    "Be",
    "Na",
    "Mg",
    "Al",
    "K",
    "Ca",
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Ga",
    "Rb",
    "Sr",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "In",
    "Sn",
    "Cs",
    "Ba",
    "Hf",
    "Ta",
    "W",
    "Re",
    "Os",
    "Ir",
    "Pt",
    "Au",
    "Hg",
    "Tl",
    "Pb",
    "Bi",
]

BOND_METHODS = ["nbo", "critic2", "OpenBabelNN + metal_edge_extender"]


def fix_C_Li_bonds(critic: Dict) -> Dict:
    """
    Adjust C-Li coordinate bonding for Critic2 calculations.

    :param critic: Critic2 output dictionary

    :return:
        critic: modified Critic2 output dictionary

    """
    for key in critic["bonding"]:
        if critic["bonding"][key]["atoms"] == ["Li", "C"] or critic["bonding"][key][
            "atoms"
        ] == ["C", "Li"]:
            if (
                critic["bonding"][key]["field"] <= 0.02
                and critic["bonding"][key]["field"] > 0.012
                and critic["bonding"][key]["distance"] < 2.5
            ):
                critic["processed"]["bonds"].append(
                    [int(entry) - 1 for entry in critic["bonding"][key]["atom_ids"]]
                )
    return critic


def _bonds_hybridization(nbo: Dict[str, Any], index: int):
    """
    Extract bonds from "hybridization_character" NBO output
    """

    bonds = set()
    warnings = set()

    if len(nbo["hybridization_character"]) > index:
        for bond_ind in nbo["hybridization_character"][index].get("type", list()):
            if nbo["hybridization_character"][index]["type"][bond_ind] != "BD":
                continue

            from_ind = (
                int(nbo["hybridization_character"][index]["atom 1 number"][bond_ind])
                - 1
            )
            to_ind = (
                int(nbo["hybridization_character"][index]["atom 2 number"][bond_ind])
                - 1
            )

            if (
                nbo["hybridization_character"][index]["atom 1 symbol"][bond_ind]
                in metals
            ):
                m_contrib = float(
                    nbo["hybridization_character"][index]["atom 1 polarization"][
                        bond_ind
                    ]
                )
            elif (
                nbo["hybridization_character"][index]["atom 2 symbol"][bond_ind]
                in metals
            ):
                m_contrib = float(
                    nbo["hybridization_character"][index]["atom 2 polarization"][
                        bond_ind
                    ]
                )
            else:
                m_contrib = None

            if m_contrib is None:
                bond_type = "covalent"
            elif m_contrib >= 30.0:
                bond_type = "covalent"
                warnings.add("Contains covalent bond with metal atom")
            else:
                bond_type = "electrostatic"

            bonds.add((from_ind, to_ind, bond_type))

    return bonds, warnings


def _bonds_peturbation(
    nbo: Dict[str, Any],
    index: int,
    poss_coord: Dict[Optional[int], List[Optional[int]]],
    energy_cutoff: float,
    metal_indices: List[int],
):
    """
    Extract bonds from "perturbation_energy" NBO output
    """

    bonds = set()  # type: ignore

    # No metals, so don't need to use perturbation analysis to get bonds
    if len(metal_indices) == 0:
        return bonds

    if len(nbo["perturbation_energy"]) > index:
        for inter_ind in nbo["perturbation_energy"][index].get("donor type", list()):
            coord = False
            m_ind: Optional[int] = None
            x_ind: Optional[int] = None
            if (
                int(
                    nbo["perturbation_energy"][index]["acceptor atom 1 number"][
                        inter_ind
                    ]
                )
                - 1
                in metal_indices
            ):
                if (
                    nbo["perturbation_energy"][index]["donor type"][inter_ind] == "LP"
                    and nbo["perturbation_energy"][index]["acceptor type"][inter_ind]
                    == "LV"
                ):
                    coord = True
                    m_ind = (
                        int(
                            nbo["perturbation_energy"][index]["acceptor atom 1 number"][
                                inter_ind
                            ]
                        )
                        - 1
                    )
                    x_ind = (
                        int(
                            nbo["perturbation_energy"][index]["donor atom 1 number"][
                                inter_ind
                            ]
                        )
                        - 1
                    )
                elif (
                    nbo["perturbation_energy"][index]["donor type"][inter_ind] == "LP"
                    and nbo["perturbation_energy"][index]["acceptor type"][inter_ind]
                    == "RY*"
                ):
                    coord = True
                    m_ind = (
                        int(
                            nbo["perturbation_energy"][index]["acceptor atom 1 number"][
                                inter_ind
                            ]
                        )
                        - 1
                    )
                    x_ind = (
                        int(
                            nbo["perturbation_energy"][index]["donor atom 1 number"][
                                inter_ind
                            ]
                        )
                        - 1
                    )
            elif (
                nbo["perturbation_energy"][index]["donor atom 1 number"][inter_ind] - 1
                in metal_indices
            ):
                if (
                    nbo["perturbation_energy"][index]["donor type"][inter_ind] == "LP"
                    and nbo["perturbation_energy"][index]["acceptor type"][inter_ind]
                    == "LV"
                ):
                    coord = True
                    m_ind = (
                        int(
                            nbo["perturbation_energy"][index]["donor atom 1 number"][
                                inter_ind
                            ]
                        )
                        - 1
                    )
                    x_ind = (
                        int(
                            nbo["perturbation_energy"][index]["acceptor atom 1 number"][
                                inter_ind
                            ]
                        )
                        - 1
                    )

            if not coord:
                continue
            elif x_ind not in poss_coord[m_ind]:
                continue

            energy = float(
                nbo["perturbation_energy"][index]["perturbation energy"][inter_ind]
            )
            if energy >= energy_cutoff:
                bonds.add((x_ind, m_ind, "electrostatic"))
    return bonds


def nbo_molecule_graph(mol: Molecule, nbo: Dict[str, Any]):
    """
    Construct a molecule graph from NBO data.

    :param mol: molecule to be analyzed
    :param nbo: Output from NBO7
    :return:
    """

    mg = MoleculeGraph.with_empty_graph(mol)

    alpha_bonds, warnings = _bonds_hybridization(nbo, 1)
    beta_bonds, new_warnings = _bonds_hybridization(nbo, 3)
    warnings = warnings.union(new_warnings)

    distance_cutoff = 3.0
    energy_cutoff = 3.0
    metal_indices = [i for i, e in enumerate(mol.species) if str(e) in metals]

    poss_coord: Dict[Optional[int], List[Optional[int]]] = dict()
    dist_mat = mol.distance_matrix
    for i in metal_indices:
        poss_coord[i] = list()
        row = dist_mat[i]
        for j, val in enumerate(row):
            if i != j and val < distance_cutoff:
                poss_coord[i].append(j)

    new_alpha_bonds = _bonds_peturbation(
        nbo, 0, poss_coord, energy_cutoff, metal_indices
    )
    alpha_bonds = alpha_bonds.union(new_alpha_bonds)

    if mol.spin_multiplicity != 1:
        new_beta_bonds = _bonds_peturbation(
            nbo, 1, poss_coord, energy_cutoff, metal_indices
        )
        beta_bonds = beta_bonds.union(new_beta_bonds)

    sorted_alpha = set([tuple(sorted([a[0], a[1]])) for a in alpha_bonds])
    sorted_beta = set([tuple(sorted([b[0], b[1]])) for b in beta_bonds])

    if sorted_alpha != sorted_beta:
        warnings.add("Difference in bonding between alpha and beta electrons")

    for bond in alpha_bonds.union(beta_bonds):
        if (bond[0], bond[1]) not in mg.graph.edges() and (
            bond[1],
            bond[0],
        ) not in mg.graph.edges():
            if bond[0] < bond[1]:
                mg.add_edge(bond[0], bond[1], edge_properties={"type": bond[2]})
            else:
                mg.add_edge(bond[1], bond[0], edge_properties={"type": bond[2]})

    mg_copy = copy.deepcopy(mg)
    mg_copy.remove_nodes(metal_indices)

    try:
        if not nx.is_connected(mg_copy.graph.to_undirected()):
            warnings.add("Metal-centered complex")
    except nx.exception.NetworkXPointlessConcept:
        if len(mg.molecule) == 1:
            warnings.add("Single-atom; no bonds")

    return (mg, list(warnings))


class MoleculeBondingDoc(PropertyDoc):
    """Representation of molecular bonding."""

    property_name: str = "bonding"

    molecule_graph: MoleculeGraph = Field(..., description="Molecule graph")

    method: str = Field(..., description="Method used to compute molecule graph")

    bond_types: Dict[str, List[float]] = Field(
        dict(),
        description="Dictionary of bond types to their length, e.g. C-O to "
        "a list of the lengths of C-O bonds in Angstrom.",
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
        molecule_id: MPculeID,
        preferred_methods: List[str],
        deprecated: bool = False,
        **kwargs,
    ):  # type: ignore[override]
        """
        Determine bonding from a task document

        Method preferences are as follows:
        - NBO7
        - OpenBabelNN + metal_edge_extender in pymatgen
        - Critic2 (really OpenBabelNN + metal_edge_extender + Critic2)

        :param task: task document from which bonding properties can be extracted
        :param molecule_id: MPculeID
        :param preferred_methods: list of methods; by default, NBO7, Critic2, and the combination
            of OpenBabelNN and metal_edge_extender in pymatgen, in that order
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        mg_made = False
        method = None
        warnings = list()

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        for m in preferred_methods:
            if mg_made:
                break

            if (
                m == "nbo"
                and task.output.nbo is not None
                and (
                    task.orig["rem"].get("run_nbo6", False)
                    or task.orig["rem"].get("nbo_external", False)
                )
            ):
                method = "nbo"
                mg, warnings = nbo_molecule_graph(mol, task.output.nbo)
                mg_made = True

            elif m == "critic2" and task.critic2 is not None:
                method = "critic2"
                critic = fix_C_Li_bonds(task.critic2)
                critic_bonds = critic["processed"]["bonds"]
                mg = make_mol_graph(mol, critic_bonds=critic_bonds)
                mg_made = True

            else:
                method = "OpenBabelNN + metal_edge_extender"
                mg = make_mol_graph(mol)
                mg_made = True

        bonds = list()
        for bond in mg.graph.edges():
            bonds.append(sorted([bond[0], bond[1]]))

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

        id_string = f"bonding-{molecule_id}-{task.task_id}-{task.lot_solvent}-{method}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        return super().from_molecule(
            meta_molecule=mol,
            property_id=property_id,
            molecule_id=molecule_id,
            level_of_theory=task.level_of_theory,
            solvent=task.solvent,
            lot_solvent=task.lot_solvent,
            method=method,
            warnings=warnings,
            molecule_graph=mg,
            bond_types=bond_types,
            bonds=bonds,
            bonds_nometal=bonds_nometal,
            origins=[PropertyOrigin(name="bonding", task_id=task.task_id)],
            deprecated=deprecated,
            **kwargs,
        )
