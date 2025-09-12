from typing_extensions import NotRequired, TypedDict

from emmet.core.types.pymatgen_types.properties import TypedSiteProperitesDict
from emmet.core.types.pymatgen_types.species_adapter import TypedSpeciesDict

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
    label: NotRequired[str | None]
    name: NotRequired[str | None]
    properties: NotRequired[TypedSiteProperitesDict | None]
    species: NotRequired[list[TypedSpeciesDict] | None]
    abc: NotRequired[list[float, float, float] | None]  # type: ignore[type-arg]
    xyz: NotRequired[list[float, float, float] | None]  # type: ignore[type-arg]
