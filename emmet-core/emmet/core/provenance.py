""" Core definition of a Provenance Document """
from datetime import datetime
from typing import ClassVar, Dict, List

from pybtex.database import BibliographyData, parse_string
from pydantic import BaseModel, EmailStr, Field, HttpUrl, validator

from emmet.core.material_property import PropertyDoc
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
        None,
        description="creation date for the first structure corresponding to this material",
    )

    projects: List[str] = Field(
        None, description="List of projects this material belongs to"
    )
    bibtex_string: str = Field(
        None, description="Bibtex reference string for this material"
    )
    remarks: List[str] = Field(
        None, description="List of remarks for the provenance of this material"
    )
    authors: List[Author] = Field(None, description="List of authors for this material")

    theoretical: bool = Field(
        True, description="If this material has any experimental provenance or not"
    )

    database_IDs: Dict[Database, List[str]] = Field(
        None, description="Database IDs corresponding to this material"
    )

    history: List[History] = Field(
        None,
        description="List of history nodes specifying the transformations or orignation of this material",
    )

    @validator("authors")
    def remove_duplicate_authors(cls, authors):
        authors_dict = {entry.name.lower(): entry for entry in authors}
        return list(authors_dict.items())
