import pymatgen.core.lattice
from pydantic import RootModel
from typing_extensions import TypedDict

MSONableTypedLatticeDict = TypedDict(
    "MSONableTypedLatticeDict",
    {
        "@module": str,
        "@class": str,
        "matrix": list[list[float, float, float]],  # type: ignore[type-arg]
        "pbc": list[bool, bool, bool],  # type: ignore[type-arg]
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
    matrix: list[list[float, float, float]]  # type: ignore[type-arg]
    pbc: list[bool, bool, bool]  # type: ignore[type-arg]
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    volume: float


class LatticeAdapter(RootModel):
    root: MSONableTypedLatticeDict


setattr(pymatgen.core.lattice.Lattice, "__type_adapter__", LatticeAdapter)
