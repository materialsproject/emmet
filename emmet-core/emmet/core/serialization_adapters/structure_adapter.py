from typing import Annotated, TypeVar

import pymatgen.core.structure
from pydantic.functional_validators import BeforeValidator
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.lattice_adapter import TypedLatticeDict
from emmet.core.serialization_adapters.properties import TypedAggregateProperitesDict
from emmet.core.serialization_adapters.sites_adapter import TypedSiteDict

TypedStructureDict = TypedDict(
    "TypedStructureDict",
    {
        "@module": str,
        "@class": str,
        "charge": int,
        "lattice": TypedLatticeDict,
        "sites": list[TypedSiteDict],
        "properties": TypedAggregateProperitesDict,
    },
)

StructureTypeVar = TypeVar(
    "StructureTypeVar", pymatgen.core.structure.Structure, TypedStructureDict
)


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

    return structure


AnnotatedStructure = Annotated[
    StructureTypeVar, BeforeValidator(pop_empty_structure_keys)
]
