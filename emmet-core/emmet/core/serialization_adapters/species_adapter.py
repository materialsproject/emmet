from typing import TypeVar

from pymatgen.core.periodic_table import Species
from typing_extensions import NotRequired, TypedDict

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
    element: NotRequired[str | None]
    oxidation_state: NotRequired[float | None]
    spin: NotRequired[float | None]
    occu: NotRequired[float | None]


SpeciesTypeVar = TypeVar("SpeciesTypeVar", Species, TypedSpeciesDict)
