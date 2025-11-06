from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.electronic_structure.bandstructure import Kpoint
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.lattice_adapter import MSONableTypedLatticeDict

TypedKpointDict = TypedDict(
    "TypedKpointDict",
    {
        "@module": str,
        "@class": str,
        "lattice": MSONableTypedLatticeDict,
        "fcoords": list[float],
        "ccoords": list[float],
        "label": str,
    },
)


KpointTypeVar = TypeVar("KpointTypeVar", Kpoint, TypedKpointDict)

KpointType = Annotated[
    KpointTypeVar,
    BeforeValidator(lambda x: Kpoint.from_dict(x) if isinstance(x, dict) else x),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedKpointDict),
]
