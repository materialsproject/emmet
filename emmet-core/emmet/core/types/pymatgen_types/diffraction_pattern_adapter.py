from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
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

DiffractionPatternType = Annotated[
    DiffractionPatternTypeVar,
    BeforeValidator(
        lambda x: DiffractionPattern.from_dict(x) if isinstance(x, dict) else x
    ),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedDiffractionPatternDict
    ),
]
