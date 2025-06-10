""" Core definition of Spectrum document """

from datetime import datetime
from typing import List

from pydantic import Field, field_validator

from emmet.core.common import convert_datetime
from emmet.core.mpid import MPID
from emmet.core.structure import StructureMetadata
from emmet.core.utils import utcnow


class SpectrumDoc(StructureMetadata):
    """
    Base model definition for any spectra document. This should contain
    metadata on the structure the spectra pertains to
    """

    spectrum_name: str

    material_id: MPID | None = Field(
        None,
        description="The ID of the material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******.",
    )

    spectrum_id: str = Field(
        ...,
        title="Spectrum Document ID",
        description="The unique ID for this spectrum document.",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property.",
        default_factory=utcnow,
    )

    warnings: List[str] = Field(
        [], description="Any warnings related to this property."
    )

    @field_validator("last_updated", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)
