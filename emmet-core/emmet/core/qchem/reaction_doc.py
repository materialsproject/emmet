""" Core definition of Reaction Documents """

from datetime import datetime
from typing import List, Sequence, Mapping, Type, TypeVar

from pydantic import BaseModel, Field

from emmet.core.qchem.reaction import Reaction, ReactionType
from emmet.core.qchem.task import TaskDoc


S = TypeVar("S", bound="ReactionDoc")


class ReactionDoc(BaseModel):
    """
    Definition for a Reaction Document
    """

    reaction_id: str = Field(
        ...,
        description="The ID of this reaction, used as a universal reference across all related Documents."
        "This comes in the form mprxn-*******",
    )

    reaction: Reaction = Field(
        ...,
        description="Reactant/product Molecules along with thermodynamic information for this Reaction.",
    )

    reactant_ids: List[str] = Field(
        ..., description="Molecule IDs for each reactant molecule"
    )

    product_ids: List[str] = Field(
        ..., description="Molecule IDs for each product molecule"
    )

    reaction_type: ReactionType = Field(..., description="Type of this reaction")

    deprecated: bool = Field(False, description="Has this molecule been deprecated?")

    task_ids: Sequence[str] = Field(
        list(),
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Reaction Document",
    )

    calc_types: Mapping[str, str] = Field(
        None,
        description="Calculation types for all the calculations that make up this reaction",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this reaction document was last updated",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this reaction document was first created",
        default_factory=datetime.utcnow,
    )

    warnings: Sequence[str] = Field(
        list(), description="Any warnings related to this reaction"
    )

    @classmethod
    def from_tasks(
            cls: TypeVar[S],
            reactants: Sequence[TaskDoc],
            products: Sequence[TaskDoc]
    ) -> S:
        pass
