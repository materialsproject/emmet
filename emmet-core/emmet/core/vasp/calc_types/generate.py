"""Module to define various calculation types as Enums for VASP."""
from __future__ import annotations
from importlib.resources import files as import_resource_files
from itertools import product

from monty.serialization import dumpfn, loadfn

_BASE_ENUM_PATH = import_resource_files("emmet.core.vasp.calc_types")

_RUN_TASK_TYPE_DATA = loadfn(str(_BASE_ENUM_PATH / "run_types.yaml"))


def generate_enum_file(enum_file_name: str | None = None) -> None:
    """
    Generate VASP enum members from reference yaml data.

    Parameters
    -----------
    enum_file_name : str
        Name of the file to write the enums to.
        Defaults to _BASE_ENUM_PATH / vasp_enums.json.gz
    """

    enum_file_name = enum_file_name or str(_BASE_ENUM_PATH / "vasp_enums.json.gz")

    _TASK_TYPES = _RUN_TASK_TYPE_DATA.get("TASK_TYPES")

    _RUN_TYPES = set(
        rt
        for functionals in _RUN_TASK_TYPE_DATA.get("RUN_TYPES", {}).values()
        for rt in functionals
    ).union(("LDA",))
    _RUN_TYPES.update(set(f"{rt}+U" for rt in _RUN_TYPES))

    _ENUMS = {
        "RunType": {
            "_".join(rt.split()).replace("+", "_").replace("-", "_"): rt
            for rt in _RUN_TYPES
        },
        "TaskType": {"_".join(tt.split()): tt for tt in _TASK_TYPES},
        "CalcType": {
            f"{'_'.join(rt.split()).replace('+','_').replace('-','_')}"
            f"_{'_'.join(tt.split())}": f"{rt} {tt}"
            for rt, tt in product(_RUN_TYPES, _TASK_TYPES)
        },
    }

    # Add docstr's
    for k in _ENUMS:
        rtc_type = k.split("Calc")[-1].split("Type")[0].lower()
        if len(rtc_type) > 0:
            rtc_type += " "
        _ENUMS[k]["__doc__"] = f"VASP calculation {rtc_type}types."

    dumpfn(_ENUMS, enum_file_name)
