""" Core definitions of molecular vibrational information """

from datetime import datetime
from typing import Dict, Sequence, List, Type, TypeVar

from pydantic import BaseModel, Field
from emmet.stubs import Composition, Molecule, Vector3D
from emmet.core.qchem.mol_entry import MoleculeEntry
from emmet.core.qchem.mol_metadata import MoleculeMetadata


T = TypeVar("T", bound="VibrationDoc")


class VibrationDoc(MoleculeMetadata):
    """
    An entry of vibrational information for a particular molecule
    """

    molecule_id: str = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across all related Documents."
        "This comes in the form mpmol-*******",
    )

    frequencies: List[float] = Field(
        None, description="Vibrational frequencies for this molecule"
    )

    vibrational_frequency_modes: List[List[Vector3D]] = Field(
        None, description="Frequency mode vectors for this molecule"
    )

    modes_ir_active: List[bool] = Field(
        None,
        description="Determination of if each mode should be considered in IR spectra",
    )

    modes_ir_intensity: List[float] = Field(
        None, description="IR intensity of vibrational frequency modes"
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
        Builds a vibration document using the minimal amount of information
        """

        return super().from_molecule(  # type: ignore
            molecule=molecule,
            molecule_id=molecule_id,
            include_structure=False,
            **kwargs
        )
