from typing_extensions import TypedDict

from emmet.core.serialization_adapters.species_adapter import MSONableTypedSpeciesDict

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
