""" Core definition of a Provenance Document """
from collections import defaultdict
from datetime import datetime
from typing import ClassVar, Dict, List, Union

from pybtex.database import BibliographyData, parse_string
from pydantic import BaseModel, EmailStr, Field, HttpUrl, validator
from pydash.objects import get
from pymatgen.util.provenance import StructureNL

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID
from emmet.core.utils import ValueEnum


class Database(ValueEnum):
    """
    Database identifiers for provenance IDs
    """

    ICSD = "icsd"
    PaulingFiles = "pf"
    COD = "cod"


class Author(BaseModel):
    """
    Author information
    """

    name: str = Field(None)
    email: EmailStr = Field(None)


class History(BaseModel):
    """
    History of the material provenance
    """

    name: str
    url: HttpUrl
    description: Dict = Field(
        None, description="Dictionary of exra data for this history node"
    )


class Provenance(PropertyDoc):
    """
    A provenance property block
    """

    property_name: ClassVar[str] = "provenance"

    created_at: datetime = Field(
        ...,
        description="creation date for the first structure corresponding to this material",
    )

    references: List[str] = Field(
        [], description="Bibtex reference strings for this material"
    )

    authors: List[Author] = Field([], description="List of authors for this material")

    remarks: List[str] = Field(
        [], description="List of remarks for the provenance of this material"
    )

    tags: List[str] = Field([])

    theoretical: bool = Field(
        True, description="If this material has any experimental provenance or not"
    )

    database_IDs: Dict[str, List[str]] = Field(
        dict(), description="Database IDs corresponding to this material"
    )

    history: List[History] = Field(
        [],
        description="List of history nodes specifying the transformations or orignation of this material for the entry closest matching the material input",
    )

    @validator("authors")
    def remove_duplicate_authors(cls, authors):
        authors_dict = {entry.name.lower(): entry for entry in authors}
        return list(authors_dict.items())
