from typing import List, Iterator
from itertools import groupby

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from emmet.core import SETTINGS


def get_sg(struc, symprec=SETTINGS.SYMPREC):
    """helper function to get spacegroup with a loose tolerance"""
    try:
        return struc.get_space_group_info(symprec=symprec)[1]
    except Exception:
        return -1


def group_structures(
    structures: List[Structure],
    ltol: float = SETTINGS.LTOL,
    stol: float = SETTINGS.STOL,
    angle_tol: float = SETTINGS.ANGLE_TOL,
    symprec: float = SETTINGS.SYMPREC,
) -> Iterator[List[Structure]]:
    """
    Groups structures according to space group and structure matching

    Args:
        structures ([Structure]): list of structures to group
        ltol (float): StructureMatcher tuning parameter for matching tasks to materials
        stol (float): StructureMatcher tuning parameter for matching tasks to materials
        angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
        symprec (float): symmetry tolerance for space group finding
    """

    sm = StructureMatcher(
        ltol=ltol,
        stol=stol,
        angle_tol=angle_tol,
        primitive_cell=True,
        scale=True,
        attempt_supercell=False,
        allow_subset=False,
        comparator=ElementComparator(),
    )

    def _get_sg(struc):
        return get_sg(struc, symprec=symprec)

    # First group by spacegroup number then by structure matching
    for sg, pregroup in groupby(sorted(structures, key=_get_sg), key=_get_sg):
        for group in sm.group_structures(list(pregroup)):
            yield group


def task_type(inputs, include_calc_type=True):
    """
    Determines the task_type

    Args:
        inputs (dict): inputs dict with an incar, kpoints, potcar, and poscar dictionaries
        include_calc_type (bool): whether to include calculation type
            in task_type such as HSE, GGA, SCAN, etc.
    """

    calc_type = []

    incar = inputs.get("incar", {})
    try:
        functional = inputs.get("potcar", {}).get("functional", "PBE")
    except:
        functional = "PBE"

    METAGGA_TYPES = {"TPSS", "RTPSS", "M06L", "MBJL", "SCAN", "MS0", "MS1", "MS2"}

    if include_calc_type:
        if incar.get("LHFCALC", False):
            calc_type.append("HSE")
        elif incar.get("METAGGA", "").strip().upper() in METAGGA_TYPES:
            calc_type.append(incar["METAGGA"].strip().upper())
        elif incar.get("LDAU", False):
            calc_type.append("GGA+U")
        elif functional == "PBE":
            calc_type.append("GGA")
        elif functional == "PW91":
            calc_type.append("PW91")
        elif functional == "Perdew-Zunger81":
            calc_type.append("LDA")

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

    elif incar.get("IBION", 0) > 6:
        calc_type.append("DFPT")

    elif incar.get("LCHIMAG", False):
        calc_type.append("NMR Nuclear Shielding")

    elif incar.get("LEFG", False):
        calc_type.append("NMR Electric Field Gradient")

    elif incar.get("NSW", 1) == 0:
        calc_type.append("Static")

    elif incar.get("ISIF", 2) == 3 and incar.get("IBRION", 0) > 0:
        calc_type.append("Structure Optimization")

    elif incar.get("ISIF", 3) == 2 and incar.get("IBRION", 0) > 0:
        calc_type.append("Deformation")

    return " ".join(calc_type)
