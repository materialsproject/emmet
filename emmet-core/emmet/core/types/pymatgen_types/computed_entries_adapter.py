from typing import Annotated, Any, TypeVar

import orjson
from pydantic import BeforeValidator, WrapSerializer
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from typing_extensions import NotRequired, TypedDict

from emmet.core.types.pymatgen_types.element_adapter import ElementType
from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)
from emmet.core.vasp.calculation import PotcarSpec

# TypedEnergyAdjustmentDict = TypedDict(
#     "TypedEnergyAdjustmentDict",
#     {
#         "@module": str,
#         "@class": str,
#         "@version": str,
#         "value": float,
#         "uncertainty": float,
#         "name": str,
#         "cls": MaterialsProject2020Compatibility | MaterialsProjectDFTMixingScheme,
#         "description": str,
#     },
# )

# TypedCompositionEnergyAdjustmentDict = TypedDict(
#     "TypedCompositionEnergyAdjustmentDict",
#     {
#         "@module": str,
#         "@class": str,
#         "@version": str,
#         "adj_per_atom": float,
#         "n_atoms": int,
#         "uncertainty_per_atom": float,
#         "name": str,
#         "cls": MaterialsProject2020Compatibility | MaterialsProjectDFTMixingScheme,
#         "description": str,
#     },
# )

# TypedTemperatureEnergyAdjustmentDict = TypedDict(
#     "TypedTemperatureEnergyAdjustmentDict",
#     {
#         "@module": str,
#         "@class": str,
#         "@version": str,
#         "adj_per_deg": float,
#         "temp": float,
#         "n_atoms": int,
#         "uncertainty_per_deg": float,
#         "name": str,
#         "cls": MaterialsProject2020Compatibility | MaterialsProjectDFTMixingScheme,
#         "description": str,
#     },
# )


class TypedCEDataDict(TypedDict):
    oxide_type: str
    aspherical: bool
    last_updated: str
    task_id: str
    material_id: str
    oxidation_states: dict[ElementType, float]
    license: str
    run_type: str


class TypedCEParameterDict(TypedDict):
    potcar_spec: list[PotcarSpec]
    run_type: str
    is_hubbard: bool
    hubbards: NotRequired[dict[str, float] | None]  # type: ignore[type-arg]


TypedComputedEntryDict = TypedDict(
    "TypedComputedEntryDict",
    {
        "@module": str,
        "@class": str,
        "energy": float,
        "composition": dict[ElementType, float],
        "entry_id": str,
        "correction": float,
        # "energy_adjustments": list[
        #     TypedCompositionEnergyAdjustmentDict
        #     | TypedEnergyAdjustmentDict
        #     | TypedTemperatureEnergyAdjustmentDict
        # ],
        "energy_adjustments": str,
        "parameters": TypedCEParameterDict,
        "data": TypedCEDataDict,
    },
)


class TypedComputedStructureEntryDict(TypedComputedEntryDict):
    structure: TypedStructureDict


ComputedEntryTypeVar = TypeVar(
    "ComputedEntryTypeVar",
    ComputedEntry,
    TypedComputedEntryDict,
)


ComputedStructureEntryTypeVar = TypeVar(
    "ComputedStructureEntryTypeVar",
    ComputedStructureEntry,
    TypedComputedStructureEntryDict,
)


def entry_serializer(entry, nxt, info) -> dict[str, Any]:
    default_serialized_object = nxt(entry.as_dict(), info)

    format = info.context.get("format") if info.context else None
    if format == "arrow":
        default_serialized_object["energy_adjustments"] = orjson.dumps(
            default_serialized_object["energy_adjustments"]
        )

    return default_serialized_object


def pop_cse_empty_keys(cse: dict) -> dict[str, Any]:
    if cse.get("structure"):
        cse["structure"] = pop_empty_structure_keys(cse["structure"])
    cse["data"] = {k: v for k, v in cse["data"].items() if v}  # type: ignore[typeddict-item]
    cse["parameters"] = {k: v for k, v in cse["parameters"].items() if v}  # type: ignore[typeddict-item]

    return cse


def entry_deserializer(entry: dict[str, Any] | ComputedEntry | ComputedStructureEntry):
    if isinstance(entry, dict):
        entry_cls: type[ComputedEntry | ComputedStructureEntry]
        match entry["@class"]:
            case "ComputedEntry":
                entry_cls = ComputedEntry
            case "ComputedStructureEntry":
                entry_cls = ComputedStructureEntry
                entry = pop_cse_empty_keys(entry)

        if isinstance(entry["energy_adjustments"], str):
            entry["energy_adjustments"] = orjson.loads(entry["energy_adjustments"])

        return entry_cls.from_dict(entry)  # type: ignore[arg-type]

    return entry


ComputedEntryType = Annotated[
    ComputedEntryTypeVar,
    BeforeValidator(entry_deserializer),
    WrapSerializer(entry_serializer, return_type=dict[str, Any]),
]


ComputedStructureEntryType = Annotated[
    ComputedStructureEntryTypeVar,
    BeforeValidator(entry_deserializer),
    WrapSerializer(entry_serializer, return_type=dict[str, Any]),
]
