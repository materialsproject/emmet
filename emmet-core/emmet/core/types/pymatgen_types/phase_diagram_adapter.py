from collections.abc import Callable
from enum import Enum, auto
from itertools import chain
from typing import Annotated, Any, TypeVar, ValuesView

import orjson
from pydantic import BeforeValidator, TypeAdapter, WrapSerializer
from pymatgen.analysis.phase_diagram import PhaseDiagram
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    TypedCEDataDict,
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
        # "el_refs": list[[str, int]],
        "el_refs_elements": list[str],
        "el_refs_entries": list[int],
        "facets": list[list[int]],
        "qhull_data": list[list[float]],
        "qhull_entries": list[int],
        "all_entries": list[TypedComputedStructureEntryDict],
    },
)

TypedPhaseDiagramDict = TypedDict(
    "TypedPhaseDiagramDict",
    {
        "@module": str,
        "@class": str,
        "elements": list[str],
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
    entries_list_serde(d["computed_data"]["all_entries"], serde_fn)

    match mode:
        case Mode.SHRED:
            el_ref_pairs = d["computed_data"].pop("el_refs")

            elements = []
            el_refs_entries = []
            for element, entry_idx in el_ref_pairs:
                elements.append(str(element))
                el_refs_entries.append(entry_idx)

            d["computed_data"]["el_refs_elements"] = elements
            d["computed_data"]["el_refs_entries"] = el_refs_entries

        case Mode.STITCH:
            elements = d["computed_data"].pop("el_refs_elements")
            el_refs_entries = d["computed_data"].pop("el_refs_entries")

            d["computed_data"]["el_refs"] = [
                (i, j) for i, j in zip(elements, el_refs_entries)
            ]


def phase_diagram_serializer(phase_diagram, nxt, info) -> dict[str, Any]:
    for entry in chain(
        phase_diagram.computed_data["qhull_entries"],
        phase_diagram.computed_data["all_entries"],
    ):
        entry.data = TypeAdapter(TypedCEDataDict).dump_python(entry.data)

    default_serialized_object = nxt(phase_diagram.as_dict(), info)

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
