import pymatgen.core.sites
from pydantic import RootModel
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
        "abc": list[float, float, float],
        "xyz": list[float, float, float],
    },
)


class TypedSiteDict(TypedDict):
    label: str
    name: str
    properties: TypedSiteProperitesDict
    species: list[TypedSpeciesDict]
    abc: list[float, float, float]
    xyz: list[float, float, float]


class SiteAdapter(RootModel):
    root: MSONableTypedSiteDict


setattr(pymatgen.core.sites.Site, "__type_adapter__", SiteAdapter)
