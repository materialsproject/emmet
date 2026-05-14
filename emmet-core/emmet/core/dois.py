from pydantic import BaseModel, Field

from emmet.core.types.typing import MaterialIdentifierType


class DOIDoc(BaseModel):
    """
    DOIs to reference specific materials on Materials Project.
    """

    doi: str | None = Field(
        None,
        description="DOI of the material.",
    )

    material_id: MaterialIdentifierType | None = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )
