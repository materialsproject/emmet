from pydantic import BaseModel, Field
from typing import Optional


class DOIDoc(BaseModel):
    """
    DOIs to reference specific materials on Materials Project.
    """

    doi: Optional[str] = Field(
        None,
        description="DOI of the material.",
    )

    bibtex: Optional[str] = Field(
        None,
        description="Bibtex reference of the material.",
    )

    task_id: Optional[str] = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )
