"""Module to define various calculation types as Enums for VASP."""
from importlib.resources import files as import_resource_files
from itertools import product

from monty.serialization import dumpfn, loadfn

_BASE_ENUM_PATH = import_resource_files("emmet.core.vasp.calc_types")

_RUN_TYPE_DATA = loadfn(str(_BASE_ENUM_PATH / "run_types.yaml"))
_TASK_TYPES = [
    "NSCF Line",
    "NSCF Uniform",
    "Dielectric",
    "DFPT",
    "DFPT Dielectric",
    "NMR Nuclear Shielding",
    "NMR Electric Field Gradient",
    "Static",
    "Structure Optimization",
    "Deformation",
    "Optic",
    "Molecular Dynamics",
    "Unrecognized",
]

_RUN_TYPES = set(
    rt for functionals in _RUN_TYPE_DATA.values() for rt in functionals
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

dumpfn(_ENUMS, str(_BASE_ENUM_PATH / "rtc_enums.json.gz"))
