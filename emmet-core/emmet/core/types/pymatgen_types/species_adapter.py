from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
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

SpeciesType = Annotated[
    SpeciesTypeVar,
    BeforeValidator(lambda x: Species.from_dict(x) if isinstance(x, dict) else x),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedSpeciesDict),
]
