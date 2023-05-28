""" Module to define various calculation types as Enums for VASP """
from pathlib import Path
from typing import Dict

from monty.serialization import loadfn
from typing_extensions import Literal

from emmet.core.vasp.calc_types.enums import CalcType, RunType, TaskType

_RUN_TYPE_DATA = loadfn(str(Path(__file__).parent.joinpath("run_types.yaml").resolve()))


def run_type(parameters: Dict) -> RunType:
    """
    Determines the run_type from the VASP parameters dict
    This is adapted from pymatgen to be far less unstable

    Args:
        parameters: Dictionary of VASP parameters from Vasprun.xml

        *** WARNING ***
        VASP mangles the LDAU* fields in the parameters field
        If you're not using the TaskDocument.run_type, copy over
        LDAU* fields from the incar rather than trust parameters
    """

    if parameters.get("LDAU", False):
        is_hubbard = "+U"
    else:
        is_hubbard = ""

    def _variant_equal(v1, v2) -> bool:
        """
        helper function to deal with strings
        """
        if isinstance(v1, str) and isinstance(v2, str):
            return v1.strip().upper() == v2.strip().upper()
        else:
            return v1 == v2

    # This is to force an order of evaluation
    for functional_class in ["HF", "VDW", "METAGGA", "GGA"]:
        for special_type, params in _RUN_TYPE_DATA[functional_class].items():
            if all(
                [
                    _variant_equal(parameters.get(param, None), value)
                    for param, value in params.items()
                ]
            ):
                return RunType(f"{special_type}{is_hubbard}")

    return RunType(f"LDA{is_hubbard}")


def task_type(
    inputs: Dict[Literal["incar", "poscar", "kpoints", "potcar"], Dict]
) -> TaskType:
    """
    Determines the task type

    Args:
        inputs: inputs dict with an incar, kpoints, potcar, and poscar dictionaries
    """

    calc_type = []

    incar = inputs.get("incar", {})

    if incar.get("ICHARG", 0) > 10:
        try:
            kpts = inputs.get("kpoints") or {}
            kpt_labels = kpts.get("labels") or []
            num_kpt_labels = len(list(filter(None.__ne__, kpt_labels)))
        except Exception as e:
            raise Exception(
                "Couldn't identify total number of kpt labels: {}".format(e)
            )

        if num_kpt_labels > 0:
            calc_type.append("NSCF Line")
        else:
            calc_type.append("NSCF Uniform")

    elif incar.get("LEPSILON", False):
        if incar.get("IBRION", 0) > 6:
            calc_type.append("DFPT")
        calc_type.append("Dielectric")

    elif incar.get("IBRION", 0) > 6:
        calc_type.append("DFPT")

    elif incar.get("LCHIMAG", False):
        calc_type.append("NMR Nuclear Shielding")

    elif incar.get("LEFG", False):
        calc_type.append("NMR Electric Field Gradient")

    elif incar.get("NSW", 1) == 0:
        if incar.get("LOPTICS", False) is True and incar.get("ALGO", None) == "Exact":
            calc_type.append("Optic")
        elif incar.get("ALGO", None) == "CHI":
            calc_type.append("Optic")
        else:
            calc_type.append("Static")

    elif incar.get("ISIF", 2) == 3 and incar.get("IBRION", 0) > 0:
        calc_type.append("Structure Optimization")

    elif incar.get("ISIF", 3) == 2 and incar.get("IBRION", 0) > 0:
        calc_type.append("Deformation")

    elif incar.get("LOPTICS", False) is True or incar.get("ALGO", None) == "CHI":
        calc_type.append("Optic")

    if len(calc_type) == 0:
        return TaskType("Unrecognized")

    return TaskType(" ".join(calc_type))


def calc_type(
    inputs: Dict[Literal["incar", "poscar", "kpoints", "potcar"], Dict],
    parameters: Dict,
) -> CalcType:
    """
    Determines the calc type

    Args:
        inputs: inputs dict with an incar, kpoints, potcar, and poscar dictionaries
        parameters: Dictionary of VASP parameters from Vasprun.xml
    """
    rt = run_type(parameters).value
    tt = task_type(inputs).value
    return CalcType(f"{rt} {tt}")
