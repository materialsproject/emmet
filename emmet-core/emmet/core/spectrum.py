""" Core definition of Spectrum document """
from datetime import datetime
from functools import partial
from typing import ClassVar, Dict, List, Union

from pydantic import Field

from emmet.core.structure import StructureMetadata


class SpectrumDoc(StructureMetadata):
    """
    Base model definition for any spectra document. This should contain
    metadata on the structure the spectra pertains to
    """

    material_id: str = Field(
        ...,
        description="The ID of the material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******",
    )

    spectrum_id: str = Field(
        ...,
        title="Spectrum Document ID",
        description="The unique ID for this spectrum document",
    )

    last_updated: datetime = Field(
        ...,
        description="Timestamp for the most recent calculation update for this property",
    )

    warnings: List[str] = Field([], description="Any warnings related to this property")

    sandboxes: List[str] = Field(
        None,
        description="List of sandboxes this spectrum belongs to."
        " Sandboxes provide a way of controlling access to spectra."
        " No sandbox means this spectrum is openly visible",
    )
