from pydantic import BaseModel, Field


class SimilarityEntry(BaseModel):
    """
    Find similar materials to a specified material based on crystal geometry.
    """

    task_id: str | None = Field(
        None,
        description="The Materials Project ID for the matched material. This comes in the form: mp-******.",
    )

    nelements: int | None = Field(
        None,
        description="Number of elements in the matched material.",
    )

    dissimilarity: float | None = Field(
        None,
        description="Dissimilarity measure for the matched material in %.",
    )

    formula: str | None = Field(
        None,
        description="Formula of the matched material.",
    )


class SimilarityDoc(BaseModel):
    """
    Model for a document containing structure similarity data
    """

    sim: list[SimilarityEntry] | None = Field(
        None,
        description="List containing similar structure data for a given material.",
    )

    material_id: str | None = Field(
        None,
        description="The Materials Project ID for the material. This comes in the form: mp-******",
    )
