import pymatgen.electronic_structure.bandstructure
from pydantic import RootModel
from pymatgen.core import Lattice, Structure
from typing_extensions import TypedDict

from emmet.core.electronic_structure import TypedBandDict


class TypedBandGapDict(TypedDict):
    direct: bool
    transition: str
    energy: float


class TypedBranchDict(TypedDict):
    start_index: int
    end_index: int
    name: str


TypedBandStructureSymmLineDict = TypedDict(
    "TypedBandStructureSymmLineDict",
    {
        "@module": str,
        "@class": str,
        "lattice_rec": Lattice,
        "efermi": float,
        "kpoints": list[list[float, float, float]],
        "bands": dict[str, list[list[float]]],
        "is_metal": bool,
        "vbm": TypedBandDict,
        "cbm": TypedBandDict,
        "band_gap": TypedBandGapDict,
        "labels_dict": dict[str, list[float]],
        "is_spin_polarized": bool,
        "projections": dict[str, list[list[list[list[float]]]]],
        "structure": Structure,
        "branches": list[TypedBranchDict],
    },
)


class BandStructureSymmLineAdapter(RootModel):
    root: TypedBandStructureSymmLineDict


setattr(
    pymatgen.electronic_structure.bandstructure.BandStructureSymmLine,
    "__type_adapter__",
    BandStructureSymmLineAdapter,
)
