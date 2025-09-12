from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.analysis.structure_matcher import StructureMatcher
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.species_adapter import MSONableTypedSpeciesDict

TypedComparatorDict = TypedDict(
    "TypedComparatorDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
    },
)  #  No concrete comparator class defines an as_dict() method, parent(Comparator) is abstract

TypedStructureMatcherDict = TypedDict(
    "TypedStructureMatcherDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "ltol": float,
        "stol": float,
        "angle_tol": float,
        "primitive_cell": bool,
        "scale": bool,
        "attempt_supercell": bool,
        "comparator": TypedComparatorDict,
        "supercell_size": str,
        "ignored_species": list[MSONableTypedSpeciesDict],
    },
)

StructureMatcherTypeVar = TypeVar(
    "StructureMatcherTypeVar", StructureMatcher, TypedStructureMatcherDict
)

StructureMatcherType = Annotated[
    StructureMatcherTypeVar,
    BeforeValidator(
        lambda x: StructureMatcher.from_dict(x) if isinstance(x, dict) else x
    ),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedStructureMatcherDict
    ),
]
