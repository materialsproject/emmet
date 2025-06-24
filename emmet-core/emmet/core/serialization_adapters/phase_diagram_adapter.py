from typing import Annotated, TypeVar

from pydantic import BeforeValidator
from pymatgen.analysis.phase_diagram import PhaseDiagram
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.computed_entries_adapter import (
    TypedComputedStructureEntryDict,
    pop_cse_empty_keys,
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
        # "el_refs": list[str, ComputedStructureEntry],
        "el_refs_elements": list[str],
        "el_refs_entries": list[TypedComputedStructureEntryDict],
        "facets": list[list[int]],
        "qhull_data": list[list[float]],
        "qhull_entries": list[TypedComputedStructureEntryDict],
        "simplexes": list[TypedSimplexDict],
    },
)

TypedPhaseDiagramDict = TypedDict(
    "TypedPhaseDiagramDict",
    {
        "@module": str,
        "@class": str,
        "all_entries": str,
        "elements": list[TypedMSONableElementDict],
        "computed_data": TypedComputedDataDict,
    },
)

PhaseDiagramTypeVar = TypeVar(
    "PhaseDiagramTypeVar", PhaseDiagram, TypedPhaseDiagramDict
)


def pop_empty_pd_keys(pd: PhaseDiagramTypeVar):
    if isinstance(pd, dict):
        pd["computed_data"]["el_refs_entries"] = [
            pop_cse_empty_keys(cse) for cse in pd["computed_data"]["el_refs_entries"]
        ]
        pd["computed_data"]["qhull_entries"] = [
            pop_cse_empty_keys(cse) for cse in pd["computed_data"]["qhull_entries"]
        ]

    return pd


AnnotatedPhaseDiagram = Annotated[
    PhaseDiagramTypeVar, BeforeValidator(pop_empty_pd_keys)
]
