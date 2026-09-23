from typing import Annotated, Any, TypeVar, cast

from pydantic import BeforeValidator, WrapSerializer
from emmet.core.io.pymatgen import GrainBoundary
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
        raw_gb = cast(dict[str, Any], gb)
        for key in ["init_cell", "oriented_unit_cell"]:
            raw_gb[key] = pop_empty_structure_keys(raw_gb[key], serialize=False)

        for site in raw_gb["sites"]:
            if "name" in site and not site["name"]:
                del site["name"]

            for key in [
                "properties",
            ]:
                properties = site.get(key) or {}
                for prop, val in list(properties.items()):
                    if val is None:
                        del properties[prop]

            for idx, species_dct in enumerate(site.get("species") or []):
                keys_to_delete = [k for k, v in species_dct.items() if v is None]
                for key in keys_to_delete:
                    del site["species"][idx][key]

        return GrainBoundary.from_dict(raw_gb)  # type: ignore[arg-type]

    return gb


GrainBoundaryType = Annotated[
    GrainBoundaryTypeVar,
    BeforeValidator(pop_empty_gb_keys),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedGrainBoundaryDict
    ),
]
