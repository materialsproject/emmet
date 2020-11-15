""" Core definitions of molecular chargeinformation """

from datetime import datetime
from typing import Dict, Sequence, List

from pydantic import BaseModel, Field
from emmet.stubs import Composition, Molecule
from emmet.core.qchem.mol_entry import MoleculeEntry


class ChargesDoc(BaseModel):
    """
    An entry of atomic partial charge information for a particular molecule
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