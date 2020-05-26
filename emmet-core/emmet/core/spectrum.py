""" Core definition of Spectrum document """
from typing import List, Dict, ClassVar, Union
from functools import partial
from datetime import datetime

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

    last_updated: datetime = Field(
        None,
        description="Timestamp for the most recent calculation update for this property",
    )

    warnings: List[str] = Field(
        None, description="Any warnings related to this property"
    )
