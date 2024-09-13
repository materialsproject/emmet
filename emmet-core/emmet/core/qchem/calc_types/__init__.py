import importlib

try:
    importlib.import_module("emmet.core.qchem.calc_types.enums")
except ImportError:
    from emmet.core.qchem.calc_types.generate import generate_enum_file

    generate_enum_file()

from emmet.core.qchem.calc_types.enums import CalcType, LevelOfTheory, TaskType
from emmet.core.qchem.calc_types.utils import (
    calc_type,
    level_of_theory,
    task_type,
    solvent,
    lot_solvent_string,
)
