from enum import Enum
from typing import Optional

from pydantic import Field
from pydantic.main import BaseModel

from emmet.core.typing import StructureType


class MPCompleteDoc(BaseModel):
    """
    Defines data for MPComplete structure submissions
    """

    structure: Optional[StructureType] = Field(
        None,
        description="Structure submitted by the user.",
    )

    public_name: Optional[str] = Field(
        None,
        description="Public name of submitter.",
    )

    public_email: Optional[str] = Field(
        None,
        description="Public email of submitter.",
    )


class MPCompleteDataStatus(Enum):
    """
    Submission status for MPComplete data
    """

    submitted = "SUBMITTED"
    pending = "PENDING"
    running = "RUNNING"
    error = "ERROR"
    complete = "COMPLETE"
