import pymatgen.analysis.phase_diagram
from pydantic import RootModel
from pymatgen.entries.computed_entries import ComputedStructureEntry
from typing_extensions import TypedDict

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
        "el_refs": list[str, ComputedStructureEntry],
        "facets": list[list[int]],
        "qhull_data": list[list[float]],
        "qhull_entries": list[ComputedStructureEntry],
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


class PhaseDiagramAdapter(RootModel):
    root: TypedPhaseDiagramDict


pymatgen.analysis.phase_diagram.PhaseDiagram.__pydantic_model__ = PhaseDiagramAdapter
