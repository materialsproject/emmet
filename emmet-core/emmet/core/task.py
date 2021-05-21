""" Core definition of a Task Document which represents a calculation from some program"""
from datetime import datetime
from typing import ClassVar, List

from pydantic import BaseModel, Field

from emmet.core.mpid import MPID


class TaskDocument(BaseModel):
    """
    Definition of Task Document
    """

    calc_code: ClassVar[str] = Field(
        ..., description="The calculation code used to compute this task"
    )
    version: str = Field(None, description="The version of the calculation code")
    dir_name: str = Field(None, description="The directory for this task")
    task_id: MPID = Field(None, description="the Task ID For this document")

    completed: bool = Field(False, description="Whether this calcuation completed")
    completed_at: datetime = Field(
        None, description="Timestamp for when this task was completed"
    )
    last_updated: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp for this task document was last updateed",
    )

    tags: List[str] = Field([], description="Metadata tags for this task document")

    warnings: List[str] = Field(
        None, description="Any warnings related to this property"
    )
