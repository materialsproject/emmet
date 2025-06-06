from typing import TypeVar

from pymatgen.electronic_structure.bandstructure import Kpoint
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.lattice_adapter import MSONableTypedLatticeDict

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
