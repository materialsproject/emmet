from typing import Annotated, TypeVar

from pydantic import BeforeValidator
from pymatgen.phonon.bandstructure import PhononBandStructureSymmLine
from pymatgen.phonon.dos import PhononDos
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.lattice_adapter import MSONableTypedLatticeDict
from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)

TypedPhononBandStructureSymmLineDict = TypedDict(
    "TypedPhononBandStructureSymmLineDict",
    {
        "@module": str,
        "@class": str,
        "bands": list[list[float]],
        "eigendisplacements": dict[str, list[list[list[list[float]]]]],
        "has_nac": bool,
        "labels_dict": dict[str, list[float, float, float]],  # type: ignore[type-arg]
        "lattice_rec": MSONableTypedLatticeDict,
        "qpoints": list[list[float]],
        "structure": TypedStructureDict,
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
        "structure": TypedStructureDict,
    },
)

PhononBandStructureSymmLineTypeVar = TypeVar(
    "PhononBandStructureSymmLineTypeVar",
    PhononBandStructureSymmLine,
    TypedPhononBandStructureSymmLineDict,
)

PhononDosTypeVar = TypeVar("PhononDosTypeVar", PhononDos, TypedPhononDosDict)


def pop_empty_keys_from_structure(
    d: PhononDosTypeVar | PhononBandStructureSymmLineTypeVar,
):
    if isinstance(d, dict):
        d["structure"] = pop_empty_structure_keys(d["structure"])

    return d


AnnotatedPhononBandStructureSymmLine = Annotated[
    PhononBandStructureSymmLineTypeVar, BeforeValidator(pop_empty_keys_from_structure)
]

AnnotatedPhononDos = Annotated[
    PhononDosTypeVar, BeforeValidator(pop_empty_keys_from_structure)
]
