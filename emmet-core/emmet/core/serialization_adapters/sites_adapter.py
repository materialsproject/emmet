from typing_extensions import TypedDict

from emmet.core.serialization_adapters.properties import TypedSiteProperitesDict
from emmet.core.serialization_adapters.species_adapter import TypedSpeciesDict

MSONableTypedSiteDict = TypedDict(
    "MSONableTypedSiteDict",
    {
        "@class": str,
        "@module": str,
        "label": str,
        "name": str,
        "properties": TypedSiteProperitesDict,
        "species": list[TypedSpeciesDict],
        "abc": list[float, float, float],  # type: ignore[type-arg]
        "xyz": list[float, float, float],  # type: ignore[type-arg]
    },
)


class TypedSiteDict(TypedDict):
    label: str
    name: str
    properties: TypedSiteProperitesDict
    species: list[TypedSpeciesDict]
    abc: list[float, float, float]  # type: ignore[type-arg]
    xyz: list[float, float, float]  # type: ignore[type-arg]
