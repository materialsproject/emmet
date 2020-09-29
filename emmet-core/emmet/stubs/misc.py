from typing import Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field
from pymatgen import Element


class Composition(BaseModel):
    """A dictionary mapping element to total quantity"""

    __root__: Dict[Element, float]


class ComputedEntry(BaseModel):
    """
    A entry of thermodynamic information for a particular composition
    """

    composition: Composition = Field(
        None, description="Full composition for this entry"
    )
    energy: float = Field(None, description="DFT total energy in eV")
    correction: float = Field(None, description="Energy correction in eV")
    energy_adjustments: List = Field(
        None,
        description="An optional list of EnergyAdjustment to be applied to the energy."
        " This is used to modify the energy for certain analyses."
        " Defaults to None.",
    )
    parameters: Dict = Field(
        None,
        description="Dictionary of extra parameters for the underlying calculation",
    )
    data: Dict = Field(None, description="Dictionary of extra data")
    entry_id: str = Field(None, description="Entry ID")
