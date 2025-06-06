from typing import Annotated, TypeVar

from pydantic import BeforeValidator
from pymatgen.core.interface import GrainBoundary
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.lattice_adapter import TypedLatticeDict
from emmet.core.serialization_adapters.sites_adapter import TypedSiteDict
from emmet.core.serialization_adapters.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)

TypedGrainBoundaryDict = TypedDict(
    "TypedGrainBoundaryDict",
    {
        "@module": str,
        "@class": str,
        "lattice": TypedLatticeDict,
        "sites": list[TypedSiteDict],
        "init_cell": TypedStructureDict,
        "rotation_axis": list[int],
        "rotation_angle": float,
        "gb_plane": list[int],
        "join_plane": list[int],
        "vacuum_thickness": float,
        "ab_shift": list[float],
        "oriented_unit_cell": TypedStructureDict,
    },
)

GrainBoundaryTypeVar = TypeVar(
    "GrainBoundaryTypeVar", GrainBoundary, TypedGrainBoundaryDict
)


def pop_empty_gb_keys(gb: GrainBoundaryTypeVar):
    if isinstance(gb, dict):
        gb["init_cell"] = pop_empty_structure_keys(gb["init_cell"])
        gb["oriented_unit_cell"] = pop_empty_structure_keys(gb["oriented_unit_cell"])

        for site in gb["sites"]:
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

    return gb


AnnotatedGrainBoundary = Annotated[
    GrainBoundaryTypeVar, BeforeValidator(pop_empty_gb_keys)
]
