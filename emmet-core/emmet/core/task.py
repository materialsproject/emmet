"""Core definition of a Task Document which represents a calculation from some program"""

from pydantic import Field

from emmet.core.base import EmmetBaseModel
from emmet.core.mpid import MPculeID
from emmet.core.types.typing import IdentifierType, DateTimeType, NullableDateTimeType


class BaseTaskDocument(EmmetBaseModel):
    """
    Definition of base Task Document
    """

    calc_code: str = Field(description="The calculation code used to compute this task")
    version: str | None = Field(None, description="The version of the calculation code")
    dir_name: str | None = Field(None, description="The directory for this task")
    task_id: IdentifierType | MPculeID | None = Field(
        None, description="the Task ID For this document"
    )

    completed: bool = Field(False, description="Whether this calcuation completed")
    completed_at: NullableDateTimeType = Field(
        description="Timestamp for when this task was completed"
    )
    last_updated: DateTimeType = Field(
        description="Timestamp for when this task document was last updated",
    )
