import pymatgen.electronic_structure.bandstructure
from pydantic import RootModel
from pymatgen.core.lattice import Lattice
from typing_extensions import TypedDict

TypedKpointDict = TypedDict(
    "TypedKpointDict",
    {
        "@module": str,
        "@class": str,
        "lattice": Lattice,
        "fcoords": list[float, float, float],  # type: ignore[type-arg]
        "ccoords": list[float, float, float],  # type: ignore[type-arg]
        "label": str,
    },
)


class KpointAdapter(RootModel):
    root: TypedKpointDict


setattr(
    pymatgen.electronic_structure.bandstructure.Kpoint,
    "__type_adapter__",
    KpointAdapter,
)
