# mypy: ignore-errors

"""Base emmet model to add default metadata."""

from datetime import datetime
from typing import Literal, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator
from pymatgen.core import __version__ as pmg_version

from emmet.core import __version__
from emmet.core.common import convert_datetime
from emmet.core.utils import utcnow

T = TypeVar("T", bound="EmmetBaseModel")


class EmmetMeta(BaseModel):
    """Default emmet metadata."""

    emmet_version: Optional[str] = Field(
        __version__, description="The version of emmet this document was built with."
    )
    pymatgen_version: Optional[str] = Field(
        pmg_version, description="The version of pymatgen this document was built with."
    )

    run_id: Optional[str] = Field(
        None, description="The run id associated with this data build."
    )

    batch_id: Optional[str] = Field(
        None,
        description="Identifier corresponding to the origin of this document's blessed task.",
    )

    database_version: Optional[str] = Field(
        None, description="The database version for the built data."
    )

    build_date: Optional[datetime] = Field(  # type: ignore
        default_factory=utcnow,
        description="The build date for this document.",
    )

    license: Optional[Literal["BY-C", "BY-NC"]] = Field(
        None, description="License for the data entry."
    )

    @field_validator("build_date", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)


class EmmetBaseModel(BaseModel):
    """Base Model for default emmet data."""

    builder_meta: Optional[EmmetMeta] = Field(
        default_factory=EmmetMeta,  # type: ignore
        description="Builder metadata.",
    )
