"""Module defining VASP calculation types."""

from emmet.core.vasp.calc_types.enums import CalcType, RunType, TaskType
from emmet.core.vasp.calc_types.utils import calc_type, run_type, task_type

__all__ = ["CalcType", "RunType", "TaskType", "calc_type", "run_type", "task_type"]
