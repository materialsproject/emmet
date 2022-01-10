""" Utilities to determine level of theory, task type, and calculation type for Q-Chem calculations"""
from pathlib import Path
from typing import Any, Dict, Optional

from monty.serialization import loadfn
from typing_extensions import Literal

from emmet.core.qchem.calc_types import LevelOfTheory, CalcType, TaskType
from emmet.core.qchem.calc_types.calc_types import (
    TASK_TYPES,
    FUNCTIONALS,
    BASIS_SETS,
    SOLVENT_MODELS,
    SOLVENTS,
    PCM_DIELECTRICS,
    SMD_PARAMETERS
)

functional_synonyms = {"wb97xd": "wb97x-d",
                       "wb97xd3": "wb97x-d3",
                       "wb97xv": "wb97x-v",
                       "wb97mv": "wb97m-v"}

def level_of_theory(
        parameters: Dict[str, Any],
        custom_smd:Optional[str]=None
) -> LevelOfTheory:
    """

    Returns the level of theory for a calculation,
    based on the input parameters given to Q-Chem

    Args:
        parameters: Dict of Q-Chem input parameters
        custom_smd: (Optional) string representing SMD parameters for a
        non-stadard solvent

    """

    funct_raw = parameters["rem"].get("method")
    basis_raw = parameters["rem"].get("basis")

    if funct_raw is None or basis_raw is None:
        raise ValueError('Method and basis must be included in "rem" section '
                         'of parameters!')

    disp_corr = parameters["rem"].get("dft_d")

    if disp_corr is None:
        funct_lower = funct_raw.lower()
        if funct_lower in functional_synonyms:
            funct_lower = functional_synonyms[funct_lower]
    elif disp_corr == "d3_bj":
        funct_lower = f"{funct_raw}-d3(bj)".lower()
    elif disp_corr == "d3_zero":
        funct_lower = f"{funct_raw}-d3(0)".lower()
    else:
        raise ValueError(f"Unexpected dispersion correction {disp_corr}!")

    basis_lower = basis_raw.lower()

    functional = None
    for f in FUNCTIONALS:
        if f.lower() == funct_lower:
            functional = f
            break
    if functional is None:
        raise ValueError(f"Unexpected functional {funct_lower}!")

    basis = None
    for b in BASIS_SETS:
        if b.lower() == basis_lower:
            basis = b
            break
    if basis is None:
        raise ValueError(f"Unexpected basis set {basis}!")

    solvent_method = parameters["rem"].get("solvent_method")
    if solvent_method is None:
        solvation = "VACUUM"
    elif solvent_method in ["pcm", "isosvp", "cosmo"]:
        dielectric = float(parameters["solvent"].get("dielectric", 78.39))
        solvent = None
        for s, d in PCM_DIELECTRICS.items():
            if round(d, 2) == round(dielectric, 2):
                solvent = s
                break

        if solvent is None:
            raise ValueError(f"Unknown solvent with dielectric {dielectric}")

        solvation = f"PCM({solvent})"
    elif solvent_method == "smd":
        solvent = parameters["smx"].get("solvent")
        if solvent is None:
            raise ValueError("No solvent provided for SMD calculation!")

        if solvent == "other":
            if custom_smd is None:
                raise ValueError("SMD calculation with solvent=other requires custom_smd!")

            match = False
            for s, p in SMD_PARAMETERS.items():
                if p == custom_smd:
                    solvent = s
                    match = True
                    break
            if not match:
                raise ValueError(f"Unknown solvent with SMD parameters {custom_smd}!")
        else:
            if solvent.upper() not in SOLVENTS:
                raise ValueError(f"Unexpected solvent {solvent.upper()}")
        solvation = f"SMD({solvent.upper()})"
    else:
        raise ValueError(f"Unexpected implicit solvent method {solvent_method}!")

    lot = f"{functional}/{basis}/{solvation}"

    return LevelOfTheory(lot)

def task_type(orig: Dict[str, Any], special_run_type: Optional[str] = None) -> TaskType:
    if special_run_type == "frequency_flattener":
        return TaskType("frequency-flattening geometry optimization")
    elif special_run_type == "ts_frequency_flattener":
        return TaskType("frequency-flattening transition-state geometry optimization")

    if orig["rem"].get("job_type") == "sp":
        return TaskType("single-point")
    elif orig["rem"].get("job_type") == "opt":
        return TaskType("geometry optimization")
    elif orig["rem"].get("job_type") == "ts":
        return TaskType("transition-state geometry optimization")
    elif orig["rem"].get("job_type") == "freq":
        return TaskType("frequency analysis")

    return TaskType("unknown")

def calc_type(
    special_run_type: str,
    orig: Dict[str, Any],
    custom_smd: Optional[str] = None
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