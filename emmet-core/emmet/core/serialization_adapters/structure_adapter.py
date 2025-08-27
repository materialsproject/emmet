from typing import Annotated, Any, TypeVar

from pydantic.functional_serializers import WrapSerializer
from pydantic.functional_validators import BeforeValidator
from pymatgen.core import Structure
from typing_extensions import NotRequired, TypedDict

from emmet.core.serialization_adapters.lattice_adapter import TypedLatticeDict
from emmet.core.serialization_adapters.properties import TypedAggregateProperitesDict
from emmet.core.serialization_adapters.sites_adapter import TypedSiteDict

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


def structure_as_dict(value: Any, handler, info) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return value.as_dict()


AnnotatedStructure = Annotated[
    StructureTypeVar,
    BeforeValidator(pop_empty_structure_keys),
    WrapSerializer(structure_as_dict),
]
