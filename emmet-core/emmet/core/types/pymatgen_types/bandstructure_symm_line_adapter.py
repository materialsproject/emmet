from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.lattice_adapter import MSONableTypedLatticeDict
from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)
from emmet.core.types.typing import TypedBandDict


class TypedBandGapDict(TypedDict):
    direct: bool
    transition: str
    energy: float


class TypedBranchDict(TypedDict):
    start_index: int
    end_index: int
    name: str


TypedBandDictureSymmLineDict = TypedDict(
    "TypedBandDictureSymmLineDict",
    {
        "@module": str,
        "@class": str,
        "lattice_rec": MSONableTypedLatticeDict,
        "efermi": float,
        "kpoints": list[list[float, float, float]],  # type: ignore[type-arg]
        "bands": dict[str, list[list[float]]],
        "is_metal": bool,
        "vbm": TypedBandDict,
        "cbm": TypedBandDict,
        "band_gap": TypedBandGapDict,
        "labels_dict": dict[str, list[float]],
        "is_spin_polarized": bool,
        "projections": dict[str, list[list[list[list[float]]]]],
        "structure": TypedStructureDict,
        "branches": list[TypedBranchDict],
    },
)

BandStructureSymmLineTypeVar = TypeVar(
    "BandStructureSymmLineTypeVar",
    BandStructureSymmLine,
    TypedBandDictureSymmLineDict,
)


def pop_empty_bs_keys(bs: BandStructureSymmLineTypeVar):
    if isinstance(bs, dict):
        bs["structure"] = pop_empty_structure_keys(bs["structure"])
        return BandStructureSymmLine.from_dict(bs)  # type: ignore[arg-type]

    return bs


BandStructureSymmLineType = Annotated[
    BandStructureSymmLineTypeVar,
    BeforeValidator(pop_empty_bs_keys),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedBandDictureSymmLineDict
    ),
]
