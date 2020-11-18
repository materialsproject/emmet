""" Core definitions of molecular charge information """

from datetime import datetime
from typing import Dict, Sequence, List, Type, TypeVar

from pydantic import BaseModel, Field
from emmet.stubs import Composition, Molecule
from emmet.core.qchem.mol_entry import MoleculeEntry
from emmet.core.qchem.mol_metadata import MoleculeMetadata


T = TypeVar("T", bound="ChargesDoc")


class ChargesDoc(MoleculeMetadata):
    """
    An entry of atomic partial charge information for a particular molecule
    """

    molecule_id: str = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across all related Documents."
        "This comes in the form mpmol-*******",
    )

    mulliken_charges: List[float] = Field(
        None,
        description="Partial charges on each atom, as determined by Mulliken population analysis",
    )

    mulliken_spin: List[float] = Field(
        None,
        description="Spin on each atom, as determined by Mulliken population analysis"
    )

    resp_charges: List[float] = Field(
        None,
        description="Molecule partial charges, as determined by the Restrained Electrostatic Potential (RESP) method",
    )

    entries: Dict[str, MoleculeEntry] = Field(
        None,
        description="List of all entries that are valid for this molecule."
        " The keys for this dictionary are names of various calculation types",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    warnings: Sequence[str] = Field(
        None, description="Any warnings related to this property"
    )

    @classmethod
    def from_molecule(  # type: ignore[override]
        cls: Type[T], molecule: Molecule, molecule_id: str, **kwargs
    ) -> T:
        """
        Builds a charges document using the minimal amount of information
        """

        return super().from_molecule(  # type: ignore
            molecule=molecule,
            molecule_id=molecule_id,
            include_structure=False,
            **kwargs
        )
