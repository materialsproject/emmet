from typing import List, Optional

from pydantic import BaseModel, Field


class SimilarityEntry(BaseModel):
    """
    Find similar materials to a specified material based on crystal geometry.
    """

    task_id: Optional[str] = Field(
        None,
        description="The Materials Project ID for the matched material. This comes in the form: mp-******.",
    )

    nelements: Optional[int] = Field(
        None,
        description="Number of elements in the matched material.",
    )

    dissimilarity: Optional[float] = Field(
        None,
        description="Dissimilarity measure for the matched material in %.",
    )

    formula: Optional[str] = Field(
        None,
        description="Formula of the matched material.",
    )


class SimilarityDoc(BaseModel):
    """
    Model for a document containing structure similarity data
    """

    sim: Optional[List[SimilarityEntry]] = Field(
        None,
        description="List containing similar structure data for a given material.",
    )

    material_id: Optional[str] = Field(
        None,
        description="The Materials Project ID for the material. This comes in the form: mp-******",
    )
