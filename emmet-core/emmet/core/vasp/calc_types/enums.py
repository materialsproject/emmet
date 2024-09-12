"""
Autogenerate enums for run, task, and calc type.

Do not edit this by hand. Edit generate.py or run_types.yaml instead.
"""
from importlib.resources import files as import_resource_files
import sys

from monty.serialization import loadfn

from emmet.core.utils import IgnoreCaseEnum

_BASE_ENUM_PATH = import_resource_files("emmet.core.vasp.calc_types") / "rtc_enums.json.gz"
for enum_name, elements in loadfn(str(_BASE_ENUM_PATH)).items():
    setattr(sys.modules[__name__], enum_name, IgnoreCaseEnum(enum_name,elements) )