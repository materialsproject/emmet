from typing import TypeVar

from pymatgen.analysis.phase_diagram import PhaseDiagram
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.computed_entries_adapter import (
    TypedComputedStructureEntryDict,
)

TypedMSONableElementDict = TypedDict(
    "TypedMSONableElementDict", {"@module": str, "@class": str, "element": str}
)

TypedSimplexDict = TypedDict(
    "TypedSimplexDict",
    {"@module": str, "@class": str, "@version": str, "coords": list[list[float]]},
)

TypedComputedDataDict = TypedDict(
    "TypedComputedDataDict",
    {
        "dim": int,
        # "el_refs": list[[str, ComputedStructureEntry]],
        "el_refs_elements": list[str],
        "el_refs_entries": list[TypedComputedStructureEntryDict],
        "facets": list[list[int]],
        "qhull_data": list[list[float]],
        "qhull_entries": list[TypedComputedStructureEntryDict],
        "simplexes": list[TypedSimplexDict],
        "all_entries": list[TypedComputedStructureEntryDict],
    },
)

TypedPhaseDiagramDict = TypedDict(
    "TypedPhaseDiagramDict",
    {
        "@module": str,
        "@class": str,
        "all_entries": list[TypedComputedStructureEntryDict],
        "elements": list[TypedMSONableElementDict],
        "computed_data": TypedComputedDataDict,
    },
)

PhaseDiagramTypeVar = TypeVar(
    "PhaseDiagramTypeVar", PhaseDiagram, TypedPhaseDiagramDict
)
