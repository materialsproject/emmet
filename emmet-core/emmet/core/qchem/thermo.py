""" Core definitions of molecular thermodynamics """

from datetime import datetime
from typing import Dict, Sequence, Type, TypeVar

from pydantic import Field
from emmet.stubs import Composition, Molecule
from emmet.core.qchem.mol_entry import MoleculeEntry
from emmet.core.qchem.mol_metadata import MoleculeMetadata


T = TypeVar("T", bound="ThermodynamicsDoc")


class ThermodynamicsDoc(MoleculeMetadata):
    """
    An entry of thermodynamic information for a particular molecule
    """

    molecule_id: str = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across all related Documents."
        "This comes in the form mpmol-*******",
    )

    energy: float = Field(None, description="DFT total energy in eV")

    enthalpy: float = Field(
        None, description="DFT-calculated total enthalpy correction in eV"
    )

    entropy: float = Field(None, description="DFT-calculated total entropy in eV/K")

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

    def free_energy(self, temperature=298.15):
        return self.energy + self.enthalpy - temperature * self.entropy

    @classmethod
    def from_molecule(  # type: ignore[override]
        cls: Type[T], molecule: Molecule, molecule_id: str, **kwargs
    ) -> T:
        """
        Builds a thermodynamics document using the minimal amount of information
        """

        return super().from_molecule(  # type: ignore
            molecule=molecule,
            molecule_id=molecule_id,
            include_structure=False,
            **kwargs
        )
