""" Module to define various calculation types as Enums for Q-Chem"""
from __future__ import annotations
from importlib.resources import files as import_resource_files
from itertools import product

from monty.serialization import dumpfn, loadfn

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


def _string_bulk_replace(string: str, rules: dict[str, str]) -> str:
    for targ_char, rep_char in rules.items():
        string = string.replace(targ_char, rep_char)
    return string


_calc_type_meta = loadfn(
    str(import_resource_files("emmet.core.qchem.calc_types") / "calc_types.yaml")
)
_calc_type_meta["FUNCTIONALS"] = [
    rt
    for functionals in _calc_type_meta["FUNCTIONAL_CLASSES"].values()
    for rt in functionals
]

_LOTS = list()

for funct in _calc_type_meta["FUNCTIONALS"]:
    for basis in _calc_type_meta["BASIS_SETS"]:
        for solv_model in _calc_type_meta["SOLVENT_MODELS"]:
            _LOTS.append(f"{funct}/{basis}/{solv_model}")

_lot_str_replacements = {"+": "_", "-": "_", "(": "_", ")": "_", "/": "_", "*": "_d"}

_ENUMS = {
    "LevelOfTheory": {
        "_".join(_string_bulk_replace(lot, _lot_str_replacements).split()): lot
        for lot in _LOTS
    },
    "TaskType": {
        "_".join(tt.split()).replace("-", "_"): tt
        for tt in _calc_type_meta["TASK_TYPES"]
    },
    "CalcType": {
        (
            "_".join(_string_bulk_replace(lot, _lot_str_replacements).split())
            + f"_{'_'.join(tt.split()).replace('-', '_')}"
        ): f"{lot} {tt}"
        for lot, tt in product(_LOTS, _calc_type_meta["TASK_TYPES"])
    },
}

for enum_name, docstr in {
    "LevelOfTheory": "Levels of theory for calculations in Q-Chem",
    "TaskType": "Calculation task types for Q-Chem",
    "CalcType": "Calculation types (LOT + task type) for Q-Chem",
}.items():
    _ENUMS[enum_name]["__doc__"] = docstr

dumpfn(
    _ENUMS,
    str(import_resource_files("emmet.core.qchem.calc_types") / "qchem_enums.json.gz"),
)
