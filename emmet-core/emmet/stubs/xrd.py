from typing import Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field
from pymatgen.core.periodic_table import Element

from emmet.core.utils import ValueEnum
from emmet.stubs import Structure


class HKL(BaseModel):

    hkl: Tuple[int, int, int] = Field(..., title="HKL Index")
    multiplicty: int = Field(..., title="The multiplicty of this HKL direction")


class XRDPattern(BaseModel):
    """
    A computed XRD pattern
    """

    x: List[float] = Field(..., title="2-Theta (degrees)")
    y: List[float] = Field(..., title="Intensity (Arbitrary Units)")
    hkls: List[List[HKL]] = Field(
        None, title="List of HKLs for each unique Diffraction peak"
    )
    d_hkls: List[float] = Field(None, title="Interplanar spacings")
