from datetime import datetime
from typing import Dict, List, Union

import numpy as np
from pydantic import Field, PyObject

from emmet.core.settings import EmmetSettings
from emmet.core.base import EmmetBaseModel
from emmet.core.mpid import MPID
from emmet.core.utils import DocEnum
from emmet.core.cp2k.task import TaskDocument

SETTINGS = EmmetSettings()


class DeprecationMessage(DocEnum):
    MANUAL = "M", "manual deprecation"
    FORCES = "C001", "Forces too large"
    CONVERGENCE = "E001", "Calculation did not converge"

class ValidationDoc(EmmetBaseModel):
    """
    Validation document for a VASP calculation
    """
    calc_code = "cp2k"

    task_id: MPID = Field(..., description="The task_id for this validation document")
    valid: bool = Field(False, description="Whether this task is valid or not")
    last_updated: datetime = Field(
        description="Last updated date for this document",
        default_factory=datetime.utcnow,
    )
    reasons: List[Union[DeprecationMessage, str]] = Field(
        None, description="List of deprecation tags detailing why this task isn't valid"
    )
    warnings: List[str] = Field(
        [], description="List of potential warnings about this calculation"
    )
    data: Dict = Field(
        description="Dictioary of data used to perform validation."
        " Useful for post-mortem analysis"
    )

    class Config:
        extra = "allow"

    @classmethod
    def from_task_doc(
        cls,
        task_doc: TaskDocument,
    ) -> "ValidationDoc":
        """

        """

        calc_type = task_doc.calc_type

        # Force check
        forces = np.array(task_doc.output.forces) > 0.05
        if np.any(forces):
            reasons = [DeprecationMessage.FORCES] 

        reasons = []
        data = {}
        warnings = []

        doc = ValidationDoc(
            task_id=task_doc.task_id,
            calc_type=calc_type,
            run_type=task_doc.run_type,
            valid=len(reasons) == 0,
            reasons=reasons,
            data=data,
            warnings=warnings,
        )
        return doc
