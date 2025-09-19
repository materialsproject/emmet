from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.core.interface import GrainBoundary
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.lattice_adapter import TypedLatticeDict
from emmet.core.types.pymatgen_types.sites_adapter import TypedSiteDict
from emmet.core.types.pymatgen_types.structure_adapter import (
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


def pop_empty_gb_keys(gb: GrainBoundaryTypeVar) -> GrainBoundary:
    if isinstance(gb, dict):
        for key in ["init_cell", "oriented_unit_cell"]:
            gb[key] = pop_empty_structure_keys(gb[key])  # type: ignore[literal-required]

        for site in gb["sites"]:
            if "name" in site and not site["name"]:
                del site["name"]

            for key in ["properties", "species"]:
                for prop, val in list(site.get(key, {}).items()):
                    if val is None:
                        del site[key][prop]

        return GrainBoundary.from_dict(gb)  # type: ignore[arg-type]

    return gb


GrainBoundaryType = Annotated[
    GrainBoundaryTypeVar,
    BeforeValidator(pop_empty_gb_keys),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedGrainBoundaryDict
    ),
]
