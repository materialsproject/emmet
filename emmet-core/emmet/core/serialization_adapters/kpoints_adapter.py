import json
from typing import Annotated, Any, TypeAlias, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.io.vasp.inputs import Kpoints
from typing_extensions import TypedDict

TypedKpointsDict = TypedDict(
    "TypedKpointsDict",
    {
        "@module": str,
        "@class": str,
        "comment": str,
        "coord_type": str,
        "generation_style": str,
        "kpoints": list[list[int]],
        "kpts_weights": list[float],
        "labels": list[str],
        "nkpoints": int,
        # "tet_connections": tuple[float, list[float]],
        "tet_connections": str,
        "tet_number": int,
        "tet_weight": float,
        "usershift": list[float],
    },
)

KpointsTypeVar = TypeVar("KpointsTypeVar", Kpoints, TypedKpointsDict)


def kpoints_deserializer(kpoints: KpointsTypeVar):
    if isinstance(kpoints, dict):
        if isinstance(kpoints["tet_connections"], str):
            kpoints["tet_connections"] = json.loads(kpoints["tet_connections"])

        return Kpoints.from_dict(kpoints)

    return kpoints


def kpoints_serializer(kpoints, nxt, info):
    default_serialized_object = kpoints.as_dict()

    format = info.context.get("format") if info.context else "standard"
    if format == "arrow" and default_serialized_object:
        default_serialized_object["tet_connections"] = json.dumps(
            default_serialized_object["tet_connections"]
        )

    return default_serialized_object


KpointsType: TypeAlias = Annotated[
    KpointsTypeVar,
    BeforeValidator(kpoints_deserializer),
    WrapSerializer(kpoints_serializer, return_type=dict[str, Any]),
]
