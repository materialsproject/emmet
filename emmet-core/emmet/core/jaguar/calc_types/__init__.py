from pathlib import Path

try:
    import emmet.core.jaguar.calc_types.enums
except ImportError:
    import emmet.core.jaguar.calc_types.generate

from emmet.core.jaguar.calc_types.enums import CalcType, LevelOfTheory, TaskType
from emmet.core.jaguar.calc_types.utils import calc_type, level_of_theory, task_type
