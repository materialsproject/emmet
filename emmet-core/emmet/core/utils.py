import datetime
from enum import Enum
from itertools import groupby
from typing import Any, Iterator, List, Tuple, Dict, Union
import copy

import bson
import numpy as np
from monty.json import MSONable
from pydantic import BaseModel
from pymatgen.analysis.structure_matcher import (
    AbstractComparator,
    ElementComparator,
    StructureMatcher,
)
from pymatgen.core.structure import Structure, Molecule

from emmet.core.settings import EmmetSettings

SETTINGS = EmmetSettings()


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
    comparator: AbstractComparator = ElementComparator(),
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
        comparator=comparator,
    )

    def _get_sg(struc):
        return get_sg(struc, symprec=symprec)

    # First group by spacegroup number then by structure matching
    for _, pregroup in groupby(sorted(structures, key=_get_sg), key=_get_sg):
        for group in sm.group_structures(list(pregroup)):
            yield group


def form_env(mol_lot: Tuple[Molecule, str]) -> str:
    """
    Get the alphabetical formula and solvent environment of a calculation
    as a string

    :param mol_lot: tuple (Molecule, str), where str is the string value of
        a LevelOfTheory object (for instance, wB97X-V/def2-TZVPPD/VACUUM)

    :returns key: str
    """

    molecule, lot = mol_lot
    lot_comp = lot.split("/")
    if lot_comp[2].upper() == "VACUUM":
        env = "VACUUM"
    else:
        env = lot_comp[2].split("(")[1].replace(")", "")

    key = molecule.composition.alphabetical_formula
    key += " " + env
    return key


def group_molecules(molecules: List[Molecule], lots: List[str]):
    """
    Groups molecules according to composition, charge, environment, and equality

    Args:
        molecules (List[Molecule])
        lots (List[str]): string representations of Q-Chem levels of theory
            (for instance, wB97X-V/def2-TZVPPD/VACUUM)
    """
    print(lots)
    for mol_key, pregroup in groupby(
        sorted(zip(molecules, lots), key=form_env), key=form_env
    ):
        subgroups: List[Dict[str, Any]] = list()
        for mol, _ in pregroup:
            mol_copy = copy.deepcopy(mol)

            # Single atoms will always have identical structure
            # So grouping by geometry isn't enough
            # Need to also group by charge
            if len(mol_copy) > 1:
                mol_copy.set_charge_and_spin(0)
            matched = False
            for subgroup in subgroups:
                if mol_copy == subgroup["mol"]:
                    subgroup["mol_list"].append(mol)
                    matched = True
                    break
            if not matched:
                subgroups.append({"mol": mol_copy, "mol_list": [mol]})
        for group in subgroups:
            yield group["mol_list"]


def confirm_molecule(mol: Union[Molecule, Dict]):
    """
    Check that something that we expect to be a molecule is actually a Molecule
    object, and not a dictionary representation.

    :param mol (Molecule):
    :return:
    """

    if isinstance(mol, Dict):
        return Molecule.from_dict(mol)
    else:
        return mol


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
    if isinstance(obj, (list, tuple, set)):
        return [jsanitize(i, strict=strict, allow_bson=allow_bson) for i in obj]
    if np is not None and isinstance(obj, np.ndarray):
        return [
            jsanitize(i, strict=strict, allow_bson=allow_bson) for i in obj.tolist()
        ]
    if isinstance(obj, Enum):
        return obj.value
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
        if np.isnan(obj):
            return 0
        return obj

    if obj is None:
        return None

    if not strict:
        return obj.__str__()

    if isinstance(obj, str):
        return obj.__str__()

    return jsanitize(obj.as_dict(), strict=strict, allow_bson=allow_bson)


class ValueEnum(Enum):
    """
    Enum that serializes to string as the value
    """

    def __str__(self):
        return str(self.value)

    def __eq__(self, o: object) -> bool:
        """Special Equals to enable converting strings back to the enum"""
        if isinstance(o, str):
            return super().__eq__(self.__class__(o))
        elif isinstance(o, self.__class__):
            return super().__eq__(o)
        return False

    def __hash__(self) -> Any:
        return super().__hash__()


class DocEnum(ValueEnum):
    """
    Enum with docstrings support
    from: https://stackoverflow.com/a/50473952
    """

    def __new__(cls, value, doc=None):
        """add docstring to the member of Enum if exists

        Args:
            value: Enum member value
            doc: Enum member docstring, None if not exists
        """
        self = object.__new__(cls)  # calling super().__new__(value) here would fail
        self._value_ = value
        if doc is not None:
            self.__doc__ = doc
        return self


def get_enum_source(enum_name, doc, items):
    header = f"""
class {enum_name}(ValueEnum):
    \"\"\" {doc} \"\"\"\n
"""
    items = [f'    {const} = "{val}"' for const, val in items.items()]

    return header + "\n".join(items)
