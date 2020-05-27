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
    def from_spectrum(
        cls,
        xas_spectrum: XAS,
        material_id: str,
        last_updated: datetime,
        warnings=None,
        **kwargs,
    ):
        spectrum_type = xas_spectrum.spectrum_type
        el = xas_spectrum.absorbing_element
        edge = xas_spectrum.edge
        xas_id = f"{material_id}-{spectrum_type}-{el}-{edge}"
        if xas_spectrum.absorbing_index is not None:
            xas_id += f"-{xas_spectrum.absorbing_index}"

        return super().from_structure(
            structure=xas_spectrum.structure,
            material_id=material_id,
            spectrum=xas_spectrum,
            edge=edge,
            spectrum_type=spectrum_type,
            absorbing_element=xas_spectrum.absorbing_element,
            xas_id=xas_id,
            last_updated=last_updated,
            warnings=warnings,
            **kwargs,
        )
