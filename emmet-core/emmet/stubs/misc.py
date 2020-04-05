from typing import Dict, List, Optional, Union, Tuple
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


class AbstractVoltagePair(BaseModel):
    """
    Based on AbstractVoltagePair from pymatgen
    """

    voltage: float = Field(
        ..., description="Voltage of voltage pair",
    )

    mAh: float = Field(
        ..., description="Energy in mAh",
    )

    mass_charge: float = Field(
        ...,
        description="Mass of charged material, normalized to one formula unit of "
        "the framework material.",
    )

    mass_discharge: float = Field(
        ...,
        description="Mass of discharged material, normalized to one formula "
        "unit of the framework material.",
    )

    vol_charge: float = Field(
        ..., description="Volume of charged pair.",
    )

    vol_discharge: float = Field(
        ..., description="Volume of discharged pair.",
    )

    frac_charge: float = Field(
        ..., description="Atomic Fraction of working ion in charged pair.",
    )

    frac_discharge: float = Field(
        ..., description="Atomic Fraction of working ion in discharged pair.",
    )

    working_ion_entry: float = Field(
        ..., description="Working ion as an entry.",
    )
