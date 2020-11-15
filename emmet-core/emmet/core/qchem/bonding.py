from typing import Mapping, TypeVar, Tuple, Set
import datetime

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
        None, description="The types of chemical bonds present in this molecule"
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
