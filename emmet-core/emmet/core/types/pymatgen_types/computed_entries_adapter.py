from typing import Annotated, Any, TypeVar

import orjson
from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    TypeAdapter,
    WrapSerializer,
    model_validator,
)
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from typing_extensions import NotRequired, TypedDict

from emmet.core.types.enums import ThermoType
from emmet.core.types.pymatgen_types.element_adapter import ElementType
from emmet.core.types.pymatgen_types.structure_adapter import (
    StructureType,
    pop_empty_structure_keys,
)
from emmet.core.types.typing import IdentifierType, MaterialIdentifierType
from emmet.core.utils import type_override
from emmet.core.vasp.calc_types.enums import RunType
from emmet.core.vasp.calculation import PotcarSpec


@type_override({"suffix": ThermoType})
class EntryID(BaseModel):
    identifier: MaterialIdentifierType
    suffix: RunType | ThermoType
    separator: str = Field(default="-")

    @model_validator(mode="before")
    def validate_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            sep = cls.model_fields["separator"].default
            parts = data.rsplit(sep, 1)
            return {"identifier": parts[0], "suffix": parts[1]}

        return data

    def __repr__(self) -> str:
        return f"EntryID(identifier={repr(self.identifier)}, suffix={repr(self.suffix)}, separator='{self.separator}')"

    def __str__(self) -> str:
        return self.separator.join([self.identifier.string, self.suffix.value])


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
    oxide_type: NotRequired[str | None]
    aspherical: NotRequired[bool | None]
    last_updated: NotRequired[str | None]
    task_id: NotRequired[IdentifierType | None]
    material_id: NotRequired[MaterialIdentifierType | None]
    oxidation_states: NotRequired[dict[ElementType, float] | None]
    license: NotRequired[str | None]
    run_type: NotRequired[str | None]


class TypedCEParameterDict(TypedDict):
    potcar_spec: NotRequired[list[PotcarSpec] | None]
    run_type: NotRequired[str | None]
    is_hubbard: NotRequired[bool | None]
    hubbards: NotRequired[dict[str, float] | None]  # type: ignore[type-arg]


# Used for running deserialization not dependent on
# type of energy_adjustments
_TypedComputedEntryDict = TypedDict(
    "TypedComputedEntryDict",
    {
        "@module": str,
        "@class": str,
        "energy": float,
        "composition": dict[ElementType, float],
        "entry_id": NotRequired[EntryID | None],
        "correction": NotRequired[float | None],
        "parameters": NotRequired[TypedCEParameterDict | None],
        "data": NotRequired[TypedCEDataDict | None],
    },
)


class TypedComputedEntryDict(_TypedComputedEntryDict):
    # energy_adjustments: list[
    #     TypedCompositionEnergyAdjustmentDict
    #     | TypedEnergyAdjustmentDict
    #     | TypedTemperatureEnergyAdjustmentDict
    # ]
    energy_adjustments: NotRequired[str | None]


class TypedComputedStructureEntryDict(TypedComputedEntryDict):
    structure: StructureType


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
    # need to beat pmg serialization to get correct (material/task/entry)_id serialization
    entry.data = TypeAdapter(TypedCEDataDict).dump_python(entry.data)

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
        entry_dict: dict[str, Any] = TypeAdapter(
            _TypedComputedEntryDict
        ).validate_python(entry, extra="allow")

        entry_cls: type[ComputedEntry | ComputedStructureEntry]
        entry_type: type[TypedComputedEntryDict | TypedComputedStructureEntryDict]

        match entry_dict["@class"]:
            case "ComputedEntry":
                entry_cls = ComputedEntry
                entry_type = TypedComputedEntryDict
            case "ComputedStructureEntry":
                entry_cls = ComputedStructureEntry
                entry_type = TypedComputedStructureEntryDict
                entry_dict = pop_cse_empty_keys(entry_dict)

        if "energy_adjustments" in entry_dict and any(
            [
                isinstance(entry_dict["energy_adjustments"], _type)
                for _type in (str, bytes)
            ]
        ):
            entry_dict = TypeAdapter(entry_type).validate_python(entry_dict)
            entry_dict["energy_adjustments"] = orjson.loads(
                entry_dict["energy_adjustments"]
            )

        return entry_cls.from_dict(entry_dict)

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
