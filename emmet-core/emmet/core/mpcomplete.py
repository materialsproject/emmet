from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import Field
from pydantic.main import BaseModel

if TYPE_CHECKING:
    from pymatgen.core.structure import Structure


class MPCompleteDoc(BaseModel):
    """Defines data for MPComplete structure submissions."""

    structure: Structure = Field(
        None,
        description="Structure submitted by the user.",
    )

    public_name: str = Field(
        None,
        description="Public name of submitter.",
    )

    public_email: str = Field(
        None,
        description="Public email of submitter.",
    )


class MPCompleteDataStatus(Enum):
    """Submission status for MPComplete data."""

    submitted = "SUBMITTED"
    pending = "PENDING"
    running = "RUNNING"
    error = "ERROR"
    complete = "COMPLETE"
