from pathlib import Path

try:
    import emmet.core.vasp.calc_types.enums
except ImportError:
    import emmet.core.vasp.calc_types.generate

from emmet.core.vasp.calc_types.enums import CalcType, RunType, TaskType
from emmet.core.vasp.calc_types.utils import calc_type, run_type, task_type
