from pydantic import Field
from pydantic.main import BaseModel

from emmet.core.types.enums import ValueEnum
from emmet.core.types.pymatgen_types.structure_adapter import StructureType


class MPCompleteDoc(BaseModel):
    """
    Defines data for MPComplete structure submissions
    """

    structure: StructureType | None = Field(
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


class MPCompleteDataStatus(ValueEnum):
    """
    Submission status for MPComplete data
    """

    submitted = "SUBMITTED"
    pending = "PENDING"
    running = "RUNNING"
    error = "ERROR"
    complete = "COMPLETE"
