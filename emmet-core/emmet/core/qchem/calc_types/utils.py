""" Utilities to determine level of theory, task type, and calculation type for Q-Chem calculations"""
from typing import Any, Dict, Optional

from emmet.core.qchem.calc_types import LevelOfTheory, CalcType, TaskType
from emmet.core.qchem.calc_types.calc_types import (
    FUNCTIONALS,
    BASIS_SETS,
    PCM_DIELECTRICS,
    SMD_PARAMETERS,
)


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


functional_synonyms = {
    "wb97xd": "wb97x-d",
    "wb97xd3": "wb97x-d3",
    "wb97xv": "wb97x-v",
    "wb97mv": "wb97m-v",
}


def level_of_theory(
    parameters: Dict[str, Any], custom_smd: Optional[str] = None
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
        raise ValueError(
            'Method and basis must be included in "rem" section ' "of parameters!"
        )

    disp_corr = parameters["rem"].get("dft_d")

    if disp_corr is None:
        funct_lower = funct_raw.lower()
        funct_lower = functional_synonyms.get(funct_lower, funct_lower)
    else:
        # Replace Q-Chem terms for D3 tails with more common expressions
        disp_corr = disp_corr.replace("_bj", "(bj)").replace("_zero", "(0)")
        funct_lower = f"{funct_raw}-{disp_corr}"

    basis_lower = basis_raw.lower()

    functional = [f for f in FUNCTIONALS if f.lower() == funct_lower]
    if not functional:
        raise ValueError(f"Unexpected functional {funct_lower}!")

    functional = functional[0]

    basis = [b for b in BASIS_SETS if b.lower() == basis_lower]
    if not basis:
        raise ValueError(f"Unexpected basis set {basis_lower}!")

    basis = basis[0]

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

        solvation = f"PCM({solvent or str(dielectric)})"
    elif solvent_method == "smd":
        solvent = parameters["smx"].get("solvent", "unknown")

        if solvent == "other":
            if custom_smd is None:
                raise ValueError(
                    "SMD calculation with solvent=other requires custom_smd!"
                )

            match = False
            custom_mod = custom_smd.replace(".0,", ".00,")
            if custom_mod.endswith(".0"):
                custom_mod += "0"
            for s, p in SMD_PARAMETERS.items():
                if p == custom_mod:
                    solvent = s
                    match = True
                    break
            if not match:
                raise ValueError(f"Unknown solvent with SMD parameters {custom_smd}!")
        solvation = f"SMD({solvent.upper()})"
    else:
        raise ValueError(f"Unexpected implicit solvent method {solvent_method}!")

    lot = f"{functional}/{basis}/{solvation}"

    return LevelOfTheory(lot)


def task_type(orig: Dict[str, Any], special_run_type: Optional[str] = None) -> TaskType:
    if special_run_type == "frequency_flattener":
        return TaskType("Frequency Flattening Geometry Optimization")
    elif special_run_type == "ts_frequency_flattener":
        return TaskType("Frequency Flattening Transition State Geometry Optimization")

    if orig["rem"].get("job_type") == "sp":
        return TaskType("Single Point")
    elif orig["rem"].get("job_type") == "opt":
        return TaskType("Geometry Optimization")
    elif orig["rem"].get("job_type") == "ts":
        return TaskType("Transition State Geometry Optimization")
    elif orig["rem"].get("job_type") == "freq":
        return TaskType("Frequency Analysis")

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
