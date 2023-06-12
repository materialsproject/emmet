from pathlib import Path

try:
    import emmet.core.cp2k.calc_types.enums
except ImportError:
    import emmet.core.cp2k.calc_types.generate

from emmet.core.cp2k.calc_types.enums import RunType, TaskType, CalcType
from emmet.core.cp2k.calc_types.utils import run_type, task_type, calc_type
