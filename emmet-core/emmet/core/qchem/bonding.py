from typing import Mapping, TypeVar, Tuple, Set, Type, Optional, Dict
from datetime import datetime

from pydantic import Field, BaseModel

from pymatgen.core.periodic_table import Element
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.anaysis.local_env import OpenBabelNN, CovalentBondNN
from pymatgen.analysis.fragmenter import metal_edge_extender
from emmet.stubs import Composition, Molecule


BondInd = Tuple[int, int]
BondInd.__doc__ = "Chemical bond between two sites in a molecule"

BondElem = Tuple[Element, Element]
BondElem.__doc__ = "Chemical bond between two elements"


S = TypeVar("S", bound="Bonding")


class Bonding(BaseModel):
    """
    An object to define the bonding in a molecule
    """

    molecule_id: str = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across all related Documents."
        "This comes in the form mpmol-*******",
    )

    molecule: Molecule = Field(..., description="The molecular structure information")

    atom_types: Mapping[int, Element] = Field(
        None, description="A mapping between site indices and elements"
    )

    bonding: Set[BondInd] = Field(
        None, description="The best bonding information available for this molecule"
    )

    bond_types: Set[BondElem] = Field(
        None, description="The types of chemical bonds present in this molecule, defined by the "
                          "best bonding information"
    )

    covalent_bonding: Set[BondInd] = Field(
        None,
        description="Molecular bonds, defined by pymatgen's covalent bond algorithm",
    )

    babel_bonding: Set[BondInd] = Field(
        None,
        description="Molecular bonds, defined by OpenBabel's bond detection algorithms",
    )

    critic_bonding: Set[BondInd] = Field(
        None,
        description="Molecular bonds, defined by the Critic2 charge density analysis",
    )

    other_bonding: Mapping[str, Set[BondInd]] = Field(
        None,
        description="Other definitions of molecular bonding, with sources/methods as keys",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    @classmethod
    def from_molecule(
            cls: Type[S],
            mol_id: str,
            molecule: Molecule,
            use_metal_edge_extender: bool = True,
            critic_bonds: Optional[Set[BondInd]] = None,
            other_bonding: Optional[Mapping[str, Set[BondInd]]] = None
    ) -> S:
        mg_cov = MoleculeGraph.with_local_env_strategy(molecule, CovalentBondNN())
        mg_bab = MoleculeGraph.with_local_env_strategy(molecule, OpenBabelNN())

        if use_metal_edge_extender:
            mg_cov = metal_edge_extender(mg_cov)
            mg_bab = metal_edge_extender(mg_bab)

        cov_bonds = {tuple(sorted(b)) for b in mg_cov.graph.edges()}
        bab_bonds = {tuple(sorted(b)) for b in mg_bab.graph.edges()}

        atom_types = dict()
        for ii, site in enumerate(molecule):
            atom_types[ii] = site.specie

        # Bonding from critic, if available, will be considered the best bonding
        if critic_bonds is not None:
            bonding = critic_bonds
        else:
            bonding = bab_bonds

        bond_types = {tuple(sorted([atom_types[a], atom_types[b]])) for a, b in bonding}

        return cls(
            molecule_id=mol_id,
            molecule=molecule,
            atom_types=atom_types,
            bonding=bonding,
            bond_types=bond_types,
            covalent_bonding=cov_bonds,
            babel_bonding=bab_bonds,
            critic_bonding=critic_bonds,
            other_bonding=other_bonding
        )

    @classmethod
    def from_molecule_graph(
            cls: Type[S],
            mol_id: str,
            mol_graph: MoleculeGraph,
            use_metal_edge_extender: bool = True,
            critic_bonds: Optional[Dict] = None,
            other_bonding: Optional[Mapping[str, Set[BondInd]]] = None) -> S:

        mg_cov = MoleculeGraph.with_local_env_strategy(mol_graph.molecule, CovalentBondNN())
        mg_bab = MoleculeGraph.with_local_env_strategy(mol_graph.molecule, OpenBabelNN())

        if use_metal_edge_extender:
            mg_cov = metal_edge_extender(mg_cov)
            mg_bab = metal_edge_extender(mg_bab)

        cov_bonds = {tuple(sorted(b)) for b in mg_cov.graph.edges()}
        bab_bonds = {tuple(sorted(b)) for b in mg_bab.graph.edges()}

        atom_types = dict()
        for ii, site in enumerate(mol_graph.molecule):
            atom_types[ii] = site.specie

        # Always use bonding from mol_graph
        bonding = {tuple(sorted(b)) for b in mol_graph.graph.edges()}
        bond_types = {tuple(sorted([atom_types[a], atom_types[b]])) for a, b in bonding}

        return cls(
            molecule_id=mol_id,
            molecule=mol_graph.molecule,
            atom_types=atom_types,
            bonding=bonding,
            bond_types=bond_types,
            covalent_bonding=cov_bonds,
            babel_bonding=bab_bonds,
            critic_bonding=critic_bonds,
            other_bonding=other_bonding
        )
