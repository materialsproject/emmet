"""Define the Materials API Response."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar, TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

from emmet.api import __version__
from emmet.core.utils import utcnow

if TYPE_CHECKING:
    from typing import Any
    from pydantic import ValidationInfo

DataT = TypeVar("DataT")


class Meta(BaseModel, extra="allow"):
    """
    Meta information for the MAPI Response.
    """

    api_version: str = Field(
        __version__,
        description="A string containing the version of the Materials API implementation, e.g. v0.9.5",
    )

    time_stamp: datetime = Field(
        description="A string containing the date and time at which the query was executed",
        default_factory=utcnow,
    )

    total_doc: int | None = Field(
        None, description="The total number of documents available for this query", ge=0
    )

    facet: dict | None = Field(
        None,
        description="A dictionary containing the facets available for this query",
    )


class Error(BaseModel):
    """Base Error model for General API."""

    code: int = Field(..., description="The error code")
    message: str = Field(..., description="The description of the error")

    @classmethod
    def from_traceback(cls, traceback):
        pass


class Response(BaseModel, Generic[DataT]):
    """
    A Generic API Response.
    """

    data: list[DataT] | None = Field(None, description="List of returned data")
    errors: list[Error] | None = Field(
        None, description="Any errors on processing this query"
    )
    meta: Meta | None = Field(None, description="Extra information for the query")

    @field_validator("errors", mode="before")
    @classmethod
    def check_consistency(cls, v, values: ValidationInfo):
        if v is not None and getattr(values, "data", None) is not None:
            raise ValueError("must not provide both data and error")
        if v is None and getattr(values, "data", None) is None:
            raise ValueError("must provide data or error")
        return v

    @field_validator("meta", mode="before")
    @classmethod
    def default_meta(cls, v: Any, values: ValidationInfo):
        if v is None or hasattr(v, "model_dump"):
            v = Meta().model_dump()  # type: ignore[call-arg]
        if v.get("total_doc", None) is None:
            v["total_doc"] = len(getattr(values, "data", []))
        return v
