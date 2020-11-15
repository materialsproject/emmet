""" Core definitions of molecular thermodynamics """

from datetime import datetime
from typing import Dict, Sequence

from pydantic import BaseModel, Field
from emmet.stubs import Composition, Molecule
from emmet.core.qchem.mol_entry import MoleculeEntry


class ThermodynamicsDoc(BaseModel):
    """
    An entry of thermodynamic information for a particular molecule
    """

    molecule_id: str = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across all related Documents."
        "This comes in the form mpmol-*******",
    )

    composition: Composition = Field(
        None, description="Full composition for this entry"
    )

    molecule: Molecule = Field(
        None, description="Molecular structure information for this entry"
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
