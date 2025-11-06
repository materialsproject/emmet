from collections.abc import Callable
from enum import Enum, auto
from typing import Annotated, Any, TypeVar, ValuesView

import orjson
from pydantic import BeforeValidator, WrapSerializer
from pymatgen.analysis.phase_diagram import PhaseDiagram
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    TypedComputedStructureEntryDict,
)


class Mode(Enum):
    SHRED = auto()
    STITCH = auto()


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


def entries_list_serde(entries_list: ValuesView | list[dict], serde_fn: Callable):
    for entry in entries_list:
        entry["energy_adjustments"] = serde_fn(entry["energy_adjustments"])


def phase_diagram_serde(d: dict, mode: Mode, serde_fn: Callable):
    entries_list_serde(d["all_entries"], serde_fn)
    for key in ["all_entries", "qhull_entries"]:
        entries_list_serde(d["computed_data"][key], serde_fn)

    match mode:
        case Mode.SHRED:
            el_ref_pairs = d["computed_data"].pop("el_refs")

            elements = []
            el_refs_entries = []
            for element, entry in el_ref_pairs:
                elements.append(str(element))
                el_refs_entries.append(entry.as_dict())

            entries_list_serde(el_refs_entries, serde_fn)

            d["computed_data"]["el_refs_elements"] = elements
            d["computed_data"]["el_refs_entries"] = el_refs_entries

        case Mode.STITCH:
            elements = d["computed_data"].pop("el_refs_elements")
            el_refs_entries = d["computed_data"].pop("el_refs_entries")

            entries_list_serde(el_refs_entries, serde_fn)

            d["computed_data"]["el_refs"] = [
                (i, j) for i, j in zip(elements, el_refs_entries)
            ]


def phase_diagram_serializer(phase_diagram, nxt, info) -> dict[str, Any]:
    default_serialized_object = nxt(phase_diagram.as_dict(), info)

    for key in ["all_entries", "qhull_entries", "simplexes"]:
        default_serialized_object["computed_data"][key] = [
            entry.as_dict() for entry in default_serialized_object["computed_data"][key]
        ]

    for simplex in default_serialized_object["computed_data"]["simplexes"]:
        simplex["coords"] = simplex["coords"].tolist()

    format = info.context.get("format") if info.context else None
    if format == "arrow":
        phase_diagram_serde(
            default_serialized_object, mode=Mode.SHRED, serde_fn=orjson.dumps
        )

    return default_serialized_object


def phase_diagram_deserializer(value) -> PhaseDiagram:
    if isinstance(value, dict):
        if all(
            key in value["computed_data"]
            for key in ["el_refs_elements", "el_refs_entries"]
        ):
            phase_diagram_serde(value, mode=Mode.STITCH, serde_fn=orjson.loads)
        return PhaseDiagram.from_dict(value)
    return value


PhaseDiagramType = Annotated[
    PhaseDiagramTypeVar,
    BeforeValidator(phase_diagram_deserializer),
    WrapSerializer(phase_diagram_serializer),
]
