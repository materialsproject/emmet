"""Core definition of Spectrum document"""

from pydantic import Field

from emmet.core.base import EmmetBaseModel
from emmet.core.structure import StructureMetadata
from emmet.core.types.typing import DateTimeType, IdentifierType


class SpectrumDoc(StructureMetadata, EmmetBaseModel):
    """
    Base model definition for any spectra document. This should contain
    metadata on the structure the spectra pertains to
    """

    spectrum_name: str

    task_id: IdentifierType | None = Field(
        None,
        description="The ID of the material, used as a universal reference across proeprty documents. "
        "This comes in an alphanumeric form.",
    )

    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent calculation update for this property.",
    )

    warnings: list[str] = Field(
        [], description="Any warnings related to this property."
    )
