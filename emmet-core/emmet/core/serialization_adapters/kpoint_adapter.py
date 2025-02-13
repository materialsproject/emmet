import pymatgen.electronic_structure.bandstructure
from pydantic import RootModel
from pymatgen.core.lattice import Lattice
from typing_extensions import TypedDict

TypedKpointDict = TypedDict(
    "TypedKpointDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "lattice": Lattice,
        "fcoords": list[float, float, float],
        "ccoords": list[float, float, float],
        "label": str,
    },
)


class KpointAdapter(RootModel):
    root: TypedKpointDict


pymatgen.electronic_structure.bandstructure.Kpoint.__pydantic_model__ = KpointAdapter
