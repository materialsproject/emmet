from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, root_validator
from pymatgen.core.periodic_table import Element

from emmet.core.spectrum import SpectrumDoc
from emmet.stubs import XAS, Structure
from emmet.stubs.xas import Edge, Type


class XASDoc(SpectrumDoc):
    """
    Document describing a XAS Spectrum.
    """

    spectrum: XAS

    xas_ids: List[str] = Field(
        ...,
        title="Calculation IDs",
        description="List of Calculations IDs used to make this XAS spectrum.",
    )

    absorbing_element: Element = Field(..., title="Absoring Element")
    spectrum_type: Type = Field(..., title="XAS Spectrum Type")
    edge: Edge = Field(
        ..., title="Absorption Edge", description="The interaction edge for XAS"
    )

    @classmethod
    def from_spectrum(
        cls,
        xas_spectrum: XAS,
        material_id: str,
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
            spectrum_id=xas_id,
            **kwargs,
        )
