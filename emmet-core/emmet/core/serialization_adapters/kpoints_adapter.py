import pymatgen.io.vasp.inputs
from pydantic import RootModel
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
        # "tet_connections": list[float, list[float]],
        "tet_connections": str,
        "tet_number": int,
        "tet_weight": float,
        "usershift": list[float],
    },
)


class KpointsAdapter(RootModel):
    root: TypedKpointsDict


setattr(pymatgen.io.vasp.inputs.Kpoints, "__type_adapter__", KpointsAdapter)
