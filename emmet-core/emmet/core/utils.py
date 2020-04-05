from typing import List, Iterator, Dict
from typing_extensions import Literal
from itertools import groupby

import datetime
import bson
import numpy as np

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from monty.serialization import loadfn
from monty.json import MSONable
from pydantic import BaseModel

from emmet.core import SETTINGS

_RUN_TYPE_DATA = loadfn("run_types.yaml")


def get_sg(struc, symprec=SETTINGS.SYMPREC) -> int:
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


def run_type(parameters: Dict) -> str:
    """
    Determines the run_type from the VASP parameters dict
    This is adapted from pymatgen to be far less unstable
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
        for special_type, params in _RUN_TYPE_DATA[functional_class]:
            if all(
                [
                    _variant_equal(parameters.get(param, None), value)
                    for param, value in params.items()
                ]
            ):
                return f"{special_type}{is_hubbard}"

    return f"LDA{is_hubbard}"


def task_type(
    inputs: Dict[Literal["incar", "poscar", "kpoints", "potcar"], Dict]
) -> str:
    """
    Determines the calculation type

    Args:
        inputs (dict): inputs dict with an incar, kpoints, potcar, and poscar dictionaries
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


def jsanitize(obj, strict=False, allow_bson=False):
    """
    This method cleans an input json-like object, either a list or a dict or
    some sequence, nested or otherwise, by converting all non-string
    dictionary keys (such as int and float) to strings, and also recursively
    encodes all objects using Monty's as_dict() protocol.
    Args:
        obj: input json-like object.
        strict (bool): This parameters sets the behavior when jsanitize
            encounters an object it does not understand. If strict is True,
            jsanitize will try to get the as_dict() attribute of the object. If
            no such attribute is found, an attribute error will be thrown. If
            strict is False, jsanitize will simply call str(object) to convert
            the object to a string representation.
        allow_bson (bool): This parameters sets the behavior when jsanitize
            encounters an bson supported type such as objectid and datetime. If
            True, such bson types will be ignored, allowing for proper
            insertion into MongoDb databases.
    Returns:
        Sanitized dict that can be json serialized.
    """
    if allow_bson and (
        isinstance(obj, (datetime.datetime, bytes))
        or (bson is not None and isinstance(obj, bson.objectid.ObjectId))
    ):
        return obj
    if isinstance(obj, (list, tuple)):
        return [jsanitize(i, strict=strict, allow_bson=allow_bson) for i in obj]
    if np is not None and isinstance(obj, np.ndarray):
        return [
            jsanitize(i, strict=strict, allow_bson=allow_bson) for i in obj.tolist()
        ]
    if isinstance(obj, dict):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.items()
        }
    if isinstance(obj, MSONable):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.as_dict().items()
        }

    if isinstance(obj, BaseModel):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.dict().items()
        }
    if isinstance(obj, (int, float)):
        return obj
    if obj is None:
        return None

    if isinstance(obj, MSONable):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.as_dict().items()
        }

    if not strict:
        return obj.__str__()

    if isinstance(obj, str):
        return obj.__str__()

    return jsanitize(obj.as_dict(), strict=strict, allow_bson=allow_bson)
