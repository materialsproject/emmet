from enum import Enum

from pydantic import Field
from pydantic.main import BaseModel
from pymatgen.core.structure import Structure


class MPCompleteDoc(BaseModel):
    """
    Defines data for MPComplete structure submissions
    """

    structure: Structure | None = Field(
        None,
        description="Structure submitted by the user.",
    )

    public_name: str | None = Field(
        None,
        description="Public name of submitter.",
    )

    public_email: str | None = Field(
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
