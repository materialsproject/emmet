""" Core definition of a Provenance Document """
import warnings
from datetime import datetime
from typing import Dict, List, Optional

from pybtex.database import BibliographyData, parse_string
from pybtex.errors import set_strict_mode
from pydantic import BaseModel, Field, root_validator, validator

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID
from emmet.core.utils import ValueEnum
from pymatgen.core.structure import Structure


class Database(ValueEnum):
    """
    Database identifiers for provenance IDs
    """

    ICSD = "icsd"
    Pauling_Files = "pf"
    COD = "cod"


class Author(BaseModel):
    """
    Author information
    """

    name: str = Field(None)
    email: str = Field(None)


class History(BaseModel):
    """
    History of the material provenance
    """

    name: str
    url: str
    description: Optional[Dict] = Field(
        None, description="Dictionary of exra data for this history node"
    )

    @root_validator(pre=True)
    def str_to_dict(cls, values):
        if isinstance(values.get("description"), str):
            values["description"] = {"string": values.get("description")}
        return values


class SNLAbout(BaseModel):
    """A data dictionary definining extra fields in a SNL"""

    references: str = Field(
        "", description="Bibtex reference strings for this material"
    )

    authors: List[Author] = Field([], description="List of authors for this material")

    remarks: List[str] = Field(
        [], description="List of remarks for the provenance of this material"
    )

    tags: List[str] = Field([])

    database_IDs: Dict[Database, List[str]] = Field(
        dict(), description="Database IDs corresponding to this material"
    )

    history: List[History] = Field(
        [],
        description="List of history nodes specifying the transformations or orignation"
        " of this material for the entry closest matching the material input",
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="The creation date for this SNL"
    )

    @validator("created_at", pre=True)
    def convert_monty_date(cls, v):
        if isinstance(v, dict):
            if v.get("@module", "datetime") and v.get("@class", "datetime"):
                return datetime.fromisoformat(v["string"])
            raise ValueError("Improper monty dict datetime")
        return v


class SNLDict(BaseModel):
    """Pydantic validated dictionary for SNL"""

    about: SNLAbout

    snl_id: str = Field(..., description="The SNL ID for this entry")


class ProvenanceDoc(PropertyDoc):
    """
    A provenance property block
    """

    property_name = "provenance"

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

    database_IDs: Dict[Database, List[str]] = Field(
        dict(), description="Database IDs corresponding to this material"
    )

    history: List[History] = Field(
        [],
        description="List of history nodes specifying the transformations or orignation"
        " of this material for the entry closest matching the material input",
    )

    @validator("authors")
    def remove_duplicate_authors(cls, authors):
        authors_dict = {entry.name.lower(): entry for entry in authors}
        return list(authors_dict.values())

    @classmethod
    def from_SNLs(
        cls, material_id: MPID, structure: Structure, snls: List[SNLDict], **kwargs
    ) -> "ProvenanceDoc":
        """
        Converts legacy Pymatgen SNLs into a single provenance document
        """

        assert (
            len(snls) > 0
        ), "Error must provide a non-zero list of SNLs to convert from SNLs"

        # Choose earliest created_at
        created_at = min([snl.about.created_at for snl in snls])
        # last_updated = max([snl.about.created_at for snl in snls])

        # Choose earliest history
        history = sorted(snls, key=lambda snl: snl.about.created_at)[0].about.history

        # Aggregate all references into one dict to remove duplicates
        refs = {}
        for snl in snls:
            try:
                set_strict_mode(False)
                entries = parse_string(snl.about.references, bib_format="bibtex")
                refs.update(entries.entries)
            except Exception as e:
                warnings.warn(
                    f"Failed parsing bibtex: {snl.about.references} due to {e}"
                )

        bib_data = BibliographyData(entries=refs)

        references = [ref.to_string("bibtex") for ref in bib_data.entries.values()]

        # TODO: Maybe we should combine this robocrystallographer?
        # TODO: Refine these tags / remarks
        remarks = list(set([remark for snl in snls for remark in snl.about.remarks]))
        tags = [r for r in remarks if len(r) < 140]

        authors = [entry for snl in snls for entry in snl.about.authors]

        # Check if this entry is experimental
        exp_vals = []
        for snl in snls:
            for entry in snl.about.history:
                if entry.description is not None:
                    exp_vals.append(entry.description.get("experimental", False))

        experimental = any(exp_vals)

        # Aggregate all the database IDs
        snl_ids = {snl.snl_id for snl in snls}
        db_ids = {
            Database(db_id): [snl_id for snl_id in snl_ids if db_id in snl_id]
            for db_id in map(str, Database)  # type: ignore
        }

        # remove Nones and empty lists
        db_ids = {k: list(filter(None, v)) for k, v in db_ids.items()}
        db_ids = {k: v for k, v in db_ids.items() if len(v) > 0}

        fields = {
            "created_at": created_at,
            "references": references,
            "authors": authors,
            "remarks": remarks,
            "tags": tags,
            "database_IDs": db_ids,
            "theoretical": not experimental,
            "history": history,
        }

        return super().from_structure(
            material_id=material_id, meta_structure=structure, **fields, **kwargs
        )
