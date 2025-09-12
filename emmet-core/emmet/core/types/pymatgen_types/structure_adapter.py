from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.core import Structure
from typing_extensions import NotRequired, TypedDict

from emmet.core.types.pymatgen_types.lattice_adapter import TypedLatticeDict
from emmet.core.types.pymatgen_types.properties import TypedAggregateProperitesDict
from emmet.core.types.pymatgen_types.sites_adapter import TypedSiteDict

TypedStructureDict = TypedDict(
    "TypedStructureDict",
    {
        "@module": str,
        "@class": str,
        "charge": NotRequired[float | None],
        "lattice": TypedLatticeDict,
        "sites": list[TypedSiteDict],
        "properties": NotRequired[TypedAggregateProperitesDict | None],
    },
)

StructureTypeVar = TypeVar("StructureTypeVar", Structure, TypedStructureDict)


def pop_empty_structure_keys(structure: StructureTypeVar):
    if isinstance(structure, dict):
        if structure.get("properties"):
            for prop, val in list(structure["properties"].items()):
                if val is None:
                    del structure["properties"][prop]

        for site in structure["sites"]:
            if "name" in site:
                if not site["name"]:
                    del site["name"]

            if site.get("properties"):
                for prop, val in list(site["properties"].items()):
                    if val is None:
                        del site["properties"][prop]

            for species in site["species"]:
                for prop, val in list(species.items()):
                    if val is None:
                        del species[prop]

        return Structure.from_dict(structure)

    return structure


StructureType = Annotated[
    StructureTypeVar,
    BeforeValidator(pop_empty_structure_keys),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedStructureDict),
]
