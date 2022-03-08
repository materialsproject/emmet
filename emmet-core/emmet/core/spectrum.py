""" Core definition of Spectrum document """
from datetime import datetime
from typing import List

from pydantic import Field

from emmet.core.mpid import MPID
from emmet.core.structure import StructureMetadata


class SpectrumDoc(StructureMetadata):
    """
    Base model definition for any spectra document. This should contain
    metadata on the structure the spectra pertains to
    """

    spectrum_name: str

    material_id: MPID = Field(
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
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    warnings: List[str] = Field([], description="Any warnings related to this property")
