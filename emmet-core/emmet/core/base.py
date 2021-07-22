""" Base emmet model to add default metadata """
from datetime import datetime
from typing import List, Optional, Type, TypeVar

from pydantic import BaseModel, Field
from pymatgen.core import __version__ as pmg_version

from emmet.core import __version__

T = TypeVar("T", bound="EmmetBaseModel")


class EmmetBaseModel(BaseModel):
    """
    Base Model for default emmet metadata
    """

    emmet_version: str = Field(
        __version__, description="The version of emmet this document was built with"
    )
    pymatgen_version: str = Field(
        pmg_version, description="The version of pymatgen this document was built with"
    )

    build_date: datetime = Field(
        default_factory=datetime.utcnow,
        description="The build date for this document",
    )
