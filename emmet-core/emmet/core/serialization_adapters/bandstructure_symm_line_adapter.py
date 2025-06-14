from typing import Annotated, TypeVar

from pydantic import BeforeValidator
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.lattice_adapter import MSONableTypedLatticeDict
from emmet.core.serialization_adapters.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)
from emmet.core.typing import TypedBandDict, TypedBandGapDict, TypedBranchDict

TypedBandStructureSymmLineDict = TypedDict(
    "TypedBandStructureSymmLineDict",
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
    TypedBandStructureSymmLineDict,
)


def pop_empty_bs_keys(bs: BandStructureSymmLineTypeVar):
    if isinstance(bs, dict):
        bs["structure"] = pop_empty_structure_keys(bs["structure"])

    return bs


AnnotatedBandStructureSymmLine = Annotated[
    BandStructureSymmLineTypeVar, BeforeValidator(pop_empty_bs_keys)
]
