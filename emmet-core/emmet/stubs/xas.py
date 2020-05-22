from enum import Enum
from typing import Dict, List, Optional, Union, Tuple
from pydantic import BaseModel, Field
from pymatgen import Element
from emmet.stubs import Structure


class Edge(Enum):
    """
    The interaction edge for XAS
    There are 2n-1 sub-components to each edge where
    K: n=1
    L: n=2
    M: n=3
    N: n=4
    """

    K = "K"
    L2 = "L2"
    L3 = "L3"
    L2_3 = "L2,3"


class Type(Enum):
    """
    The type of XAS Spectrum
    XANES - Just the near-edge region
    EXAFS - Just the extended region
    XAFS - Fully stitchted XANES + EXAFS
    """

    XANES = "XANES"
    EXAFS = "EXAFS"
    XAFS = "XAFS"


class XASSpectrum(BaseModel):
    """
    An XAS Spectrum
    """

    x: List[float] = Field(None, title="X-ray energy")
    y: List[float] = Field(None, title="Absorption (Arbitrary Units)")
    structure: Optional[Structure] = Field(None, title="Structure")
    absorbing_element: Optional[Element] = Field(None, title="Absoring Element")
    absorbing_index: Optional[int] = Field(
        None,
        title="Absoring Index",
        description="Site index for the absorbing element if this is a site-specific spectrum",
    )
    spectrum_type: Type = Field(None, title="XAS Spectrum Type")
    edge: Edge = Field(
        None, title="Absorption Edge", description="The interaction edge for XAS"
    )
