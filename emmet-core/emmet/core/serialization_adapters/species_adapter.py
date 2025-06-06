from typing import TypeVar

from pymatgen.core.periodic_table import Species
from typing_extensions import TypedDict

MSONableTypedSpeciesDict = TypedDict(
    "MSONableTypedSpeciesDict",
    {
        "@module": str,
        "@class": str,
        "element": str,
        "oxidation_state": float,
        "spin": float,
    },
)


class TypedSpeciesDict(TypedDict):
    element: str
    oxidation_state: float
    spin: float
    occu: int


SpeciesTypeVar = TypeVar("SpeciesTypeVar", Species, TypedSpeciesDict)
