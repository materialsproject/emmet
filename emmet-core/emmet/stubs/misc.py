from typing import Dict, List, Optional, Union, Tuple
from pydantic import BaseModel, Field
from pymatgen import Element
Composition = Dict[Element, float]
Composition.__doc__ = """A dictionary mapping element to total quantity"""


class ComputedEntry(BaseModel):
    """
    A Thermo Entry
    """

    composition: Composition = Field(
        None, description="Full composition for this entry"
    )
    energy_per_atom: float = Field(
        None, description="DFT total energy per atom in eV/atom"
    )
    energy: float = Field(None, description="DFT total energy in eV")
    correction: float = Field(None, description="Energy correction in eV")
    parameters: Dict = Field(
        None,
        description="Dictionary of extra parameters for the underlying calculation",
    )
    data: Dict = Field(None, description="Dictionary of extra data")
    entry_id: str = Field(None, description="Entry ID")