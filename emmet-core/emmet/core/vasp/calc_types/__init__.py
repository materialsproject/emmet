"""Module defining vasp calculation types."""

import importlib

try:
    importlib.import_module("emmet.core.vasp.calc_types.enums")
except ImportError:
    from emmet.core.vasp.calc_types.generate import generate_enum_file

    generate_enum_file()

from emmet.core.vasp.calc_types.enums import CalcType, RunType, TaskType
from emmet.core.vasp.calc_types.utils import calc_type, run_type, task_type
