from pathlib import Path

if not Path(__file__).parent.joinpath("enums.py").exists:
    import emmet.core.vasp.calc_types.generate

from emmet.core.vasp.calc_types.enums import RunType, TaskType, CalcType
from emmet.core.vasp.calc_types.utils import run_type, task_type, calc_type
