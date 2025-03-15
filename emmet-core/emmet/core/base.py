# mypy: ignore-errors

"""Base emmet model to add default metadata."""

from datetime import datetime
from typing import Literal, Optional, TypeVar

import pyarrow as pa
from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    field_validator,
    model_serializer,
)
from pymatgen.core import __version__ as pmg_version

from emmet.core import __version__
from emmet.core.common import convert_datetime
from emmet.core.utils import jsanitize, utcnow

T = TypeVar("T", bound="EmmetBaseModel")


class ArrowModel(BaseModel):
    @classmethod
    def arrow_type(cls):
        from emmet.core.arrow import arrowize

        return arrowize(cls)

    @classmethod
    def from_arrow(cls, arrow_struct):
        from emmet.core.arrow import cleanup_msonables

        data = cleanup_msonables(
            jsanitize(arrow_struct.as_py(maps_as_pydicts="strict"))
        )
        return cls(**{k: v for k, v in data.items()})

    @model_serializer(mode="wrap")
    def model_serialization(self, default_serializer, info: SerializationInfo):
        default_serialized_model = default_serializer(self, info)

        format = info.context.get("format") if info.context else "standard"
        if format == "arrow":
            return pa.scalar(
                jsanitize(default_serialized_model, allow_bson=True),
                type=self.arrow_type(),
            )

        return default_serialized_model


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


class EmmetBaseModel(ArrowModel):
    """Base Model for default emmet data."""

    builder_meta: Optional[EmmetMeta] = Field(
        default_factory=EmmetMeta,  # type: ignore
        description="Builder metadata.",
    )
