from pydantic import BaseModel, Field
from typing import Optional


class SubstratesDoc(BaseModel):
    """
    Possible growth substrates for a given material.
    """

    sub_form: Optional[str] = Field(
        None,
        description="Reduced formula of the substrate.",
    )

    sub_id: Optional[str] = Field(
        None,
        description="Materials Project ID of the substrate material. This comes in the form: mp-******.",
    )

    film_orient: Optional[str] = Field(
        None,
        description="Surface orientation of the film material.",
    )

    area: Optional[float] = Field(
        None,
        description="Minimum coincident interface area in Å².",
    )

    energy: Optional[float] = Field(
        None,
        description="Elastic energy in meV.",
    )

    film_id: Optional[str] = Field(
        None,
        description="The Materials Project ID of the film material. This comes in the form: mp-******.",
    )

    norients: Optional[int] = Field(
        None,
        description="Number of possible surface orientations for the substrate.",
        alias="_norients",
    )

    orient: Optional[str] = Field(
        None,
        description="Surface orientation of the substrate material.",
    )
