from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.core import Lattice
from typing_extensions import NotRequired, TypedDict

MSONableTypedLatticeDict = TypedDict(
    "MSONableTypedLatticeDict",
    {
        "@module": str,
        "@class": str,
        "matrix": list[list[float]],
        "pbc": tuple[bool, bool, bool],
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
    pbc: NotRequired[tuple[bool, bool, bool] | None]
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    volume: float


LatticeTypeVar = TypeVar("LatticeTypeVar", Lattice, MSONableTypedLatticeDict)

LatticeType = Annotated[
    LatticeTypeVar,
    BeforeValidator(lambda x: Lattice.from_dict(x) if isinstance(x, dict) else x),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=MSONableTypedLatticeDict
    ),
]
