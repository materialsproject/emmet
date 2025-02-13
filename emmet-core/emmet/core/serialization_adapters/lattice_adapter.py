import pymatgen.core.lattice
from pydantic import RootModel
from typing_extensions import TypedDict

MSONableTypedLatticeDict = TypedDict(
    "MSONableTypedLatticeDict",
    {
        "@module": str,
        "@class": str,
        "matrix": list[list[float, float, float]],
        "pbc": list[bool, bool, bool],
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
    matrix: list[list[float, float, float]]
    pbc: list[bool, bool, bool]
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    volume: float


class LatticeAdapter(RootModel):
    root: MSONableTypedLatticeDict


pymatgen.core.lattice.Lattice.__pydantic_model__ = LatticeAdapter
