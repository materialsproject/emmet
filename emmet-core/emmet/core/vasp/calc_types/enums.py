"""
Autogenerate enums for run, task, and calc type.

Do not edit this by hand. Edit generate.py or run_types.yaml instead.
"""
from importlib.resources import files as import_resource_files
from monty.serialization import loadfn
from emmet.core.utils import IgnoreCaseEnum

_BASE_ENUM_PATH = import_resource_files("emmet.core.vasp.calc_types") / "rtc_enums.json.gz"
_VASP_ENUMS = loadfn(str(_BASE_ENUM_PATH))
RunType = IgnoreCaseEnum("RunType",_VASP_ENUMS.get("RunType"))
TaskType = IgnoreCaseEnum("TaskType",_VASP_ENUMS.get("TaskType"))
CalcType = IgnoreCaseEnum("CalcType",_VASP_ENUMS.get("CalcType"))