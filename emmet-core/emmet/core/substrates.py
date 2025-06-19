from pydantic import BaseModel, Field


class SubstratesDoc(BaseModel):
    """
    Possible growth substrates for a given material.
    """

    sub_form: str | None = Field(
        None,
        description="Reduced formula of the substrate.",
    )

    sub_id: str | None = Field(
        None,
        description="Materials Project ID of the substrate material. This comes in the form: mp-******.",
    )

    film_orient: str | None = Field(
        None,
        description="Surface orientation of the film material.",
    )

    area: float | None = Field(
        None,
        description="Minimum coincident interface area in Å².",
    )

    energy: float | None = Field(
        None,
        description="Elastic energy in meV.",
    )

    film_id: str | None = Field(
        None,
        description="The Materials Project ID of the film material. This comes in the form: mp-******.",
    )

    norients: int | None = Field(
        None,
        description="Number of possible surface orientations for the substrate.",
        alias="_norients",
    )

    orient: str | None = Field(
        None,
        description="Surface orientation of the substrate material.",
    )
