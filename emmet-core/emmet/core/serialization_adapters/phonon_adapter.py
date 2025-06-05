import pymatgen.phonon.bandstructure
import pymatgen.phonon.dos
from pydantic import RootModel
from pymatgen.core.lattice import Lattice
from pymatgen.core.structure import Structure
from typing_extensions import TypedDict

TypedPhononBandStructureSymmLineDict = TypedDict(
    "TypedPhononBandStructureSymmLineDict",
    {
        "@module": str,
        "@class": str,
        "bands": list[list[float]],
        "eigendisplacements": dict[str, list[list[list[list[float]]]]],
        "has_nac": bool,
        "labels_dict": dict[str, list[float, float, float]],  # type: ignore[type-arg]
        "lattice_rec": Lattice,
        "qpoints": list[list[float]],
        "structure": Structure,
    },
)

TypedPhononDosDict = TypedDict(
    "TypedPhononDosDict",
    {
        "@module": str,
        "@class": str,
        "densities": list[float],
        "frequencies": list[float],
        "pdos": list[list[float]],
        "structure": Structure,
    },
)


class PhononBandStructureSymmLineAdapter(RootModel):
    root: TypedPhononBandStructureSymmLineDict


class PhononDosAdapter(RootModel):
    root: TypedPhononDosDict


setattr(
    pymatgen.phonon.bandstructure.PhononBandStructureSymmLine,
    "__type_adapter__",
    PhononBandStructureSymmLineAdapter,
)
setattr(pymatgen.phonon.dos.PhononDos, "__type_adapter__", PhononDosAdapter)
