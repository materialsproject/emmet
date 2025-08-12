from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field, validator

from maggma import __version__

""" Describes the Materials API Response """


DataT = TypeVar("DataT")


class Meta(BaseModel):
    """
    Meta information for the MAPI Response.
    """

    api_version: str = Field(
        __version__,
        description="a string containing the version of the Materials API implementation, e.g. v0.9.5",
    )

    time_stamp: datetime = Field(
        description="a string containing the date and time at which the query was executed",
        default_factory=datetime.utcnow,
    )

    total_doc: Optional[int] = Field(
        None, description="the total number of documents available for this query", ge=0
    )

    facet: Optional[dict] = Field(
        None,
        description="a dictionary containing the facets available for this query",
    )

    class Config:
        extra = "allow"


class Error(BaseModel):
    """
    Base Error model for General API.
    """

    code: int = Field(..., description="The error code")
    message: str = Field(..., description="The description of the error")

    @classmethod
    def from_traceback(cls, traceback):
        pass


class Response(BaseModel, Generic[DataT]):
    """
    A Generic API Response.
    """

    data: Optional[list[DataT]] = Field(None, description="List of returned data")
    errors: Optional[list[Error]] = Field(
        None, description="Any errors on processing this query"
    )
    meta: Optional[Meta] = Field(None, description="Extra information for the query")

    @validator("errors", always=True)
    def check_consistency(cls, v, values):
        if v is not None and values["data"] is not None:
            raise ValueError("must not provide both data and error")
        if v is None and values.get("data") is None:
            raise ValueError("must provide data or error")
        return v

    @validator("meta", pre=True, always=True)
    def default_meta(cls, v, values):
        if v is None:
            v = Meta().dict()
        if v.get("total_doc", None) is None:
            if values.get("data", None) is not None:
                v["total_doc"] = len(values["data"])
            else:
                v["total_doc"] = 0
        return v


class S3URLDoc(BaseModel):
    """
    S3 pre-signed URL data returned by the S3 URL resource.
    """

    url: str = Field(
        ...,
        description="Pre-signed download URL",
    )

    requested_datetime: datetime = Field(
        ..., description="Datetime for when URL was requested"
    )

    expiry_datetime: datetime = Field(..., description="Expiry datetime of the URL")
