from typing import Annotated, Any, TypeAlias, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.io.vasp.inputs import Kpoints
from typing_extensions import NotRequired, TypedDict

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
        "sym_weight": NotRequired[list[float]],  # tet_connections
        "tet_vertices": NotRequired[list[list[float]]],  # tet_connections
        "tet_number": int,
        "tet_weight": float,
        "usershift": list[float],
    },
)

KpointsTypeVar = TypeVar("KpointsTypeVar", Kpoints, TypedKpointsDict)


def kpoints_deserializer(kpoints: KpointsTypeVar):
    if isinstance(kpoints, dict):
        if "sym_weight" in kpoints:
            kpoints["tet_connections"] = [  # type: ignore[typeddict-unknown-key]
                (sym, vert)
                for sym, vert in zip(kpoints["sym_weight"], kpoints["tet_vertices"])
            ]
            del kpoints["sym_weight"]
            del kpoints["tet_vertices"]

        return Kpoints.from_dict(kpoints)  # type: ignore[arg-type]

    return kpoints


def kpoints_serializer(kpoints, nxt, info):
    default_serialized_object = kpoints.as_dict()

    format = info.context.get("format") if info.context else None
    if format == "arrow" and default_serialized_object:
        if default_serialized_object["tet_connections"]:
            default_serialized_object["sym_weight"] = [
                conn[0] for conn in default_serialized_object["tet_connections"]
            ]
            default_serialized_object["tet_vertices"] = [
                conn[1] for conn in default_serialized_object["tet_connections"]
            ]

        del default_serialized_object["tet_connections"]

    return default_serialized_object


KpointsType: TypeAlias = Annotated[
    KpointsTypeVar,
    BeforeValidator(kpoints_deserializer),
    WrapSerializer(kpoints_serializer, return_type=dict[str, Any]),
]
