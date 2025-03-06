import pymatgen.analysis.structure_matcher
from pydantic import RootModel
from pymatgen.core import Species
from typing_extensions import TypedDict

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
        "ignored_species": list[Species],
    },
)


class StructureMatcherAdapter(RootModel):
    root: TypedStructureMatcherDict


pymatgen.analysis.structure_matcher.StructureMatcher.__pydantic_model__ = (
    StructureMatcherAdapter
)
