import pymatgen.analysis.diffraction.xrd
from pydantic import RootModel
from typing_extensions import TypedDict


class TypedHKLDict(TypedDict):
    hkl: list[int]
    multiplicity: int


TypedDiffractionPattern = TypedDict(
    "TypedDiffractionPattern",
    {
        "@module": str,
        "@class": str,
        "x": list[float],
        "y": list[float],
        "hkls": list[list[TypedHKLDict]],
        "d_hkls": list[float],
    },
)


class DiffractionPatternAdapter(RootModel):
    root: TypedDiffractionPattern


setattr(
    pymatgen.analysis.diffraction.xrd.DiffractionPattern,
    "__type_adapter__",
    DiffractionPatternAdapter,
)
