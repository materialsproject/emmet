"""Base emmet model to add default metadata."""

from datetime import datetime
from typing import Literal, TypeVar

from pydantic import BaseModel, Field, field_validator
from pymatgen.core import __version__ as pmg_version

from emmet.core import ARROW_COMPATIBLE, __version__
from emmet.core.common import convert_datetime
from emmet.core.utils import utcnow

if ARROW_COMPATIBLE:
    from emmet.core.arrow import arrowize

T = TypeVar("T", bound="EmmetBaseModel")


class ContextModel(BaseModel):
    @classmethod
    def arrow_type(cls):
        if not ARROW_COMPATIBLE:
            raise RuntimeError(
                "pyarrow must be installed to generate arrow type defs for emmet models"
            )
        return arrowize(cls)


class EmmetMeta(BaseModel):
    """Default emmet metadata."""

    emmet_version: str | None = Field(
        __version__, description="The version of emmet this document was built with."
    )
    pymatgen_version: str | None = Field(
        pmg_version, description="The version of pymatgen this document was built with."
    )

    run_id: str | None = Field(
        None, description="The run id associated with this data build."
    )

    batch_id: str | None = Field(
        None,
        description="Identifier corresponding to the origin of this document's blessed task.",
    )

    database_version: str | None = Field(
        None, description="The database version for the built data."
    )

    build_date: datetime | None = Field(  # type: ignore
        default_factory=utcnow,
        description="The build date for this document.",
    )

    license: Literal["BY-C", "BY-NC"] | None = Field(
        None, description="License for the data entry."
    )

    @field_validator("build_date", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)


class EmmetBaseModel(ContextModel):
    """Base Model for default emmet data."""

    builder_meta: EmmetMeta | None = Field(
        default_factory=EmmetMeta,  # type: ignore
        description="Builder metadata.",
    )


class CalcMeta(BaseModel):
    """Lightweight representation for storing jobflow-style job info."""

    identifier: str | None = Field(
        None, description="The identifier (UUID, ULID, etc.) of the calculation."
    )
    dir_name: str | None = Field(
        None, description="The file-systm-like path where a job was run."
    )
    name: str | None = Field(
        None, description="The job name or a convenient label for it."
    )
    parents: list[str] | None = Field(
        None, description="A list of all UUIDs which fed into this job."
    )
