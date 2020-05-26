from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from pymatgen import Element

from emmet.core.spectrum import SpectrumDoc
from emmet.stubs import Structure, XAS
from emmet.stubs.xas import Edge, Type


class XASDoc(SpectrumDoc):
    """
    Document describing a XAS Spectrum.
    """

    spectrum: Optional[XAS] = None

    xas_id: str = Field(
        None, title="XAS Document ID", description="The unique ID for this XAS document"
    )

    xas_ids: List[str] = Field(
        None,
        title="Calculation IDs",
        description="List of Calculations IDs used to make this XAS spectrum.",
    )

    absorbing_element: Element = Field(None, title="Absoring Element")
    spectrum_type: Type = Field(None, title="XAS Spectrum Type")
    edge: Edge = Field(
        None, title="Absorption Edge", description="The interaction edge for XAS"
    )

    @classmethod
    def from_spectrum(cls, xas_spectrum: XAS, **kwargs):

        return super().from_structure(
            structure=xas_spectrum.structure, spectrum=xas_spectrum, **kwargs
        )
