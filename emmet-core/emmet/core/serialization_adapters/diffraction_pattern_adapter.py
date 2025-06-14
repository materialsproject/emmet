from typing import TypeVar

from pymatgen.analysis.diffraction.xrd import DiffractionPattern
from typing_extensions import TypedDict


class TypedHKLDict(TypedDict):
    hkl: list[int]
    multiplicity: int


TypedDiffractionPatternDict = TypedDict(
    "TypedDiffractionPatternDict",
    {
        "@module": str,
        "@class": str,
        "x": list[float],
        "y": list[float],
        "hkls": list[list[TypedHKLDict]],
        "d_hkls": list[float],
    },
)

DiffractionPatternTypeVar = TypeVar(
    "DiffractionPatternTypeVar", DiffractionPattern, TypedDiffractionPatternDict
)
