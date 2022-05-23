""" Utilities to determine level of theory, task type, and calculation type for Q-Chem calculations"""
from typing import Any, Dict, Optional

from emmet.core.jaguar.calc_types import LevelOfTheory, CalcType, TaskType
from emmet.core.jaguar.calc_types.calc_types import (
    FUNCTIONALS,
    BASIS_SETS,
    SOLVENTS,
    PCM_DIELECTRICS,
    SMD_PARAMETERS,
)


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


def level_of_theory(parameters: Dict[str, Any]) -> LevelOfTheory:
    """

    Returns the level of theory for a calculation,
    based on the input parameters given to Jaguar

    Args:
        parameters: Dict of Jaguar input parameters
    """

    funct_raw = parameters["gen_variables"].get("dftname")
    basis_raw = parameters["gen_variables"].get("basis")

    if funct_raw is None or basis_raw is None:
        raise ValueError(
            'Method and basis must be included in "gen_variables" section of parameters!'
        )

    funct_lower = funct_raw.lower()
    basis_lower = basis_raw.lower()

    functional = [f for f in FUNCTIONALS if f.lower() == funct_lower]
    if not functional:
        raise ValueError(f"Unexpected functional {funct_lower}!")

    functional = functional[0]

    basis = [b for b in BASIS_SETS if b.lower() == basis_lower]
    if not basis:
        raise ValueError(f"Unexpected basis set {basis_lower}!")

    basis = basis[0]


    solvation = parameters.get("solvation", False)
    if not solvation:
        solvent_method = "VACUUM"
    else:
        solvent_method = f"PCM(WATER)"

    lot = f"{functional}/{basis}/{solvation}"

    return LevelOfTheory(lot)


def task_type(job_type: str) -> TaskType:
    if job_type == "sp":
        return TaskType("Single Point")
    elif job_type == "opt":
        return TaskType("Geometry Optimization")
    elif job_type == "ts":
        return TaskType("Transition State Geometry Optimization")
    elif job_type == "freq":
        return TaskType("Frequency Analysis")
    elif job_type == "scan":
        return TaskType("Potential Energy Surface Scan")
    elif job_type == "irc":
        return TaskType("Intrinsic Reaction Coordinate")

    return TaskType("Unknown")


def calc_type(
    special_run_type: str, orig: Dict[str, Any], custom_smd: Optional[str] = None
) -> CalcType:
    """
    Determines the calc type

    Args:
        inputs: inputs dict with an incar, kpoints, potcar, and poscar dictionaries
        parameters: Dictionary of VASP parameters from Vasprun.xml
    """
    rt = level_of_theory(orig, custom_smd=custom_smd).value
    tt = task_type(orig, special_run_type=special_run_type).value
    return CalcType(f"{rt} {tt}")
