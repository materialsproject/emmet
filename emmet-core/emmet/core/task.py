"""Core definition of a Task Document which represents a calculation from some program"""

from datetime import datetime

from pydantic import Field

from emmet.core.base import EmmetBaseModel
from emmet.core.mpid import AlphaID, MPID, MPculeID
from emmet.core.utils import utcnow


class BaseTaskDocument(EmmetBaseModel):
    """
    Definition of base Task Document
    """

    calc_code: str = Field(description="The calculation code used to compute this task")
    version: str | None = Field(None, description="The version of the calculation code")
    dir_name: str | None = Field(None, description="The directory for this task")
    task_id: MPID | AlphaID | MPculeID | None = Field(
        None, description="the Task ID For this document"
    )

    completed: bool = Field(False, description="Whether this calcuation completed")
    completed_at: datetime | None = Field(
        None, description="Timestamp for when this task was completed"
    )
    last_updated: datetime = Field(
        default_factory=utcnow,
        description="Timestamp for when this task document was last updated",
    )
