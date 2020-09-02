from datetime import datetime
from enum import Enum
from typing import Dict

from pydantic import BaseModel, Field


class DocEnum(Enum):
    """Enum with docstrings support"""

    def __new__(cls, value, doc=None):
        """add docstring to the member of Enum if exists

        Args:
            value: Enum member value
            doc: Enum member docstring, None if not exists
        """
        obj = str.__new__(cls, value)
        if doc:
            obj.__doc__ = doc
        return obj


class DeprecationMessage(DocEnum):

    kpoints = "kpoints", "Too few Kpoints"
    encut = "encut", "ENCUT too low"
    ldau = "ldau", "LDAU parameters don't match"
    manual = "manual", "Manually deprecated"


class ValidationDoc(BaseModel):
    """
    Validation document for a VASP calculation
    """

    task_id: str = Field(..., description="The task_id for this validation document")
    valid: bool = Field(False, description="Whether this task is valid or not")
    last_updated: datetime = Field(
        description="Last updated date for this document",
        default_factory=datetime.utcnow,
    )
    reasons: List[DeprecationMessage] = Field(
        {}, description="List of deprecation tags detailing why this task isn't valid"
    )
