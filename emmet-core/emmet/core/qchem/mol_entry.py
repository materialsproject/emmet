""" Core definitions of a MoleculeEntry """

from typing import Dict

from pydantic import BaseModel, Field
from emmet.stubs import Composition, Molecule


class MoleculeEntry(BaseModel):
    """
    An entry of thermodynamic information for a particular molecule
    """

    entry_id: str = Field(None, description="Entry ID")

    composition: Composition = Field(
        None, description="Full composition for this entry"
    )

    molecule: Molecule = Field(
        None, description="Molecular structure information for this entry"
    )

    energy: float = Field(None, description="DFT total energy in eV")

    parameters: Dict = Field(
        None,
        description="Dictionary of extra parameters for the underlying calculation",
    )

    data: Dict = Field(None, description="Dictionary of extra data")
