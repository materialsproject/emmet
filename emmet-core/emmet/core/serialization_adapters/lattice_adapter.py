from typing import TypeVar

from pymatgen.core import Lattice
from typing_extensions import TypedDict

MSONableTypedLatticeDict = TypedDict(
    "MSONableTypedLatticeDict",
    {
        "@module": str,
        "@class": str,
        "matrix": list[list[float]],
        "pbc": list[bool],
        "a": float,
        "b": float,
        "c": float,
        "alpha": float,
        "beta": float,
        "gamma": float,
        "volume": float,
    },
)


class TypedLatticeDict(TypedDict):
    matrix: list[list[float]]
    pbc: list[bool]
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    volume: float


LatticeTypeVar = TypeVar("LatticeTypeVar", Lattice, MSONableTypedLatticeDict)
