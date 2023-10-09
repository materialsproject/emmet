# mypy: ignore-errors

""" Base emmet model to add default metadata """
from datetime import datetime
from typing import TypeVar, Optional, Literal

from pydantic import field_validator, BaseModel, Field
from pymatgen.core import __version__ as pmg_version
from monty.json import MontyDecoder

from emmet.core import __version__

T = TypeVar("T", bound="EmmetBaseModel")

monty_decoder = MontyDecoder()


class EmmetMeta(BaseModel):
    """
    Default emmet metadata
    """

    emmet_version: str = Field(
        __version__, description="The version of emmet this document was built with."
    )
    pymatgen_version: str = Field(
        pmg_version, description="The version of pymatgen this document was built with."
    )

    pull_request: Optional[int] = Field(
        None, description="The pull request number associated with this data build."
    )

    database_version: Optional[str] = Field(
        None, description="The database version for the built data."
    )

    build_date: datetime = Field(
        default_factory=datetime.utcnow,
        description="The build date for this document.",
    )

    license: Optional[Literal["BY-C", "BY-NC"]] = Field(
        None, description="License for the data entry."
    )

    # Make sure that the datetime field is properly formatted
    @field_validator("build_date", mode="before")
    @classmethod
    def build_date_dict_ok(cls, v):
        return monty_decoder.process_decoded(v)


class EmmetBaseModel(BaseModel):
    """
    Base Model for default emmet data
    """

    builder_meta: EmmetMeta = Field(
        default_factory=EmmetMeta, description="Builder metadata."
    )
