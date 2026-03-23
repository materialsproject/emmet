from collections.abc import Callable
from itertools import chain
from typing import Annotated, Any, TypeVar

import orjson
from pydantic import BeforeValidator, TypeAdapter, WrapSerializer
from pymatgen.apps.battery.conversion_battery import (
    ConversionElectrode,
    ConversionVoltagePair,
)
from pymatgen.apps.battery.insertion_battery import (
    InsertionElectrode,
    InsertionVoltagePair,
)
from typing_extensions import TypedDict

from emmet.core.types.enums import BatteryType
from emmet.core.types.pymatgen_types.balanced_reaction_adapter import (
    TypedBalancedReactionDict,
)
from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    TypedCEDataDict,
    TypedComputedEntryDict,
    TypedComputedStructureEntryDict,
    pop_cse_empty_keys,
)

_MSONables = TypedDict(
    "_MSONables",
    {
        "@module": str,
        "@class": str,
    },
)


class BaseVoltagePairDict(_MSONables):
    voltage: float
    frac_charge: float
    frac_discharge: float
    framework_formula: str
    mAh: float
    mass_charge: float
    mass_discharge: float
    vol_charge: float
    vol_discharge: float


class TypedInsertionVoltagePairDict(BaseVoltagePairDict):
    working_ion_entry: TypedComputedEntryDict
    entry_charge: TypedComputedStructureEntryDict
    entry_discharge: TypedComputedStructureEntryDict


TypedInsertionElectrodeDict = TypedDict(
    "TypedInsertionElectrodeDict",
    {
        "@module": str,
        "@class": str,
        "framework_formula": str,
        "stable_entries": list[TypedComputedStructureEntryDict],
        "unstable_entries": list[TypedComputedStructureEntryDict],
        "voltage_pairs": list[TypedInsertionVoltagePairDict],
        "working_ion_entry": TypedComputedEntryDict,
    },
)

InsertionElectrodeTypeVar = TypeVar(
    "InsertionElectrodeTypeVar",
    InsertionElectrode,
    TypedInsertionElectrodeDict,
)


class TypedConversionVoltagePairDict(BaseVoltagePairDict):
    working_ion_entry: TypedComputedStructureEntryDict
    entries_charge: list[TypedComputedStructureEntryDict]
    entries_discharge: list[TypedComputedStructureEntryDict]
    rxn: TypedBalancedReactionDict


TypedConversionElectrodeDict = TypedDict(
    "TypedConversionElectrodeDict",
    {
        "@module": str,
        "@class": str,
        "framework_formula": str,
        "initial_comp_formula": str,
        "voltage_pairs": list[TypedConversionVoltagePairDict],
        "working_ion_entry": TypedComputedStructureEntryDict,
    },
)

ConversionElectrodeTypeVar = TypeVar(
    "ConversionElectrodeTypeVar",
    ConversionElectrode,
    TypedConversionElectrodeDict,
)


def walk_voltage_pairs(voltage_pairs: list[dict[str, Any]], battery_type: BatteryType):
    pair: dict[str, Any]
    voltage_pair_cls: type[InsertionVoltagePair | ConversionVoltagePair]

    match battery_type:
        case BatteryType.insertion:
            voltage_pair_cls = InsertionVoltagePair
            for pair in voltage_pairs:
                for key in ["entry_charge", "entry_discharge", "working_ion_entry"]:
                    pair[key] = pop_cse_empty_keys(pair[key])

        case BatteryType.conversion:
            voltage_pair_cls = ConversionVoltagePair
            for pair in voltage_pairs:
                for key in ["entries_charge", "entries_discharge"]:
                    pair[key] = [pop_cse_empty_keys(cse) for cse in pair[key]]

    return [voltage_pair_cls.from_dict(vp) for vp in voltage_pairs]


def electrode_object_energy_adjustments_serde(
    electrode_object: dict,
    battery_type: BatteryType,
    serde_fn: Callable,
    ea="energy_adjustments",
):
    pair: dict[str, Any]

    electrode_object["working_ion_entry"][ea] = serde_fn(
        electrode_object["working_ion_entry"][ea]
    )

    match battery_type:
        case BatteryType.insertion:
            for pair in electrode_object["voltage_pairs"]:
                for key in ["working_ion_entry", "entry_charge", "entry_discharge"]:
                    pair[key][ea] = serde_fn(pair[key][ea])

            for key in ["stable_entries", "unstable_entries"]:
                for entry in electrode_object[key]:
                    entry[ea] = serde_fn(entry[ea])

        case BatteryType.conversion:
            for pair in electrode_object["voltage_pairs"]:
                pair["working_ion_entry"][ea] = serde_fn(pair["working_ion_entry"][ea])
                for key in ["entries_charge", "entries_discharge"]:
                    for entry in pair[key]:
                        entry[ea] = serde_fn(entry[ea])


def _serialize_entry_data_field(electrode_object, battery_type):
    match battery_type:
        case BatteryType.insertion:
            for entry in chain(
                electrode_object.stable_entries, electrode_object.unstable_entries
            ):
                entry.data = TypeAdapter(TypedCEDataDict).dump_python(entry.data)

            for pair in electrode_object.voltage_pairs:
                pair.working_ion_entry.data = TypeAdapter(TypedCEDataDict).dump_python(
                    pair.working_ion_entry.data
                )
                pair.entry_charge.data = TypeAdapter(TypedCEDataDict).dump_python(
                    pair.entry_charge.data
                )
                pair.entry_discharge.data = TypeAdapter(TypedCEDataDict).dump_python(
                    pair.entry_discharge.data
                )

        case BatteryType.conversion:
            for pair in electrode_object.voltage_pairs:
                pair.working_ion_entry.data = TypeAdapter(TypedCEDataDict).dump_python(
                    pair.working_ion_entry.data
                )
                for entry in chain(pair.entries_charge, pair.entries_discharge):
                    entry.data = TypeAdapter(TypedCEDataDict).dump_python(entry.data)

    electrode_object.working_ion_entry.data = TypeAdapter(TypedCEDataDict).dump_python(
        electrode_object.working_ion_entry.data
    )

    return electrode_object


def electrode_object_serializer(electrode_object, nxt, info) -> dict[str, Any]:
    battery_type = (
        BatteryType.insertion
        if electrode_object.__class__.__name__ == "InsertionElectrode"
        else BatteryType.conversion
    )

    # need to beat pmg serialization to get correct (material/task/entry)_id serialization
    electrode_object = _serialize_entry_data_field(electrode_object, battery_type)

    default_serialized_object = nxt(electrode_object.as_dict(), info)

    format = info.context.get("format") if info.context else None
    if format == "arrow":
        electrode_object_energy_adjustments_serde(
            default_serialized_object, battery_type, orjson.dumps
        )

    return default_serialized_object


def _deserialize_electrode_object_entries(electrode_object, battery_type):
    match battery_type:
        case BatteryType.insertion:
            electrode_object["working_ion_entry"] = TypeAdapter(
                TypedComputedEntryDict
            ).validate_python(electrode_object["working_ion_entry"])

            electrode_object["stable_entries"] = [
                TypeAdapter(TypedComputedStructureEntryDict).validate_python(entry)
                for entry in electrode_object["stable_entries"]
            ]
            electrode_object["unstable_entries"] = [
                TypeAdapter(TypedComputedStructureEntryDict).validate_python(entry)
                for entry in electrode_object["unstable_entries"]
            ]

            for pair in electrode_object["voltage_pairs"]:
                for key, _type in [
                    ("working_ion_entry", TypedComputedEntryDict),
                    ("entry_charge", TypedComputedStructureEntryDict),
                    ("entry_discharge", TypedComputedStructureEntryDict),
                ]:
                    pair[key] = TypeAdapter(_type).validate_python(pair[key])

        case BatteryType.conversion:
            electrode_object["working_ion_entry"] = TypeAdapter(
                TypedComputedStructureEntryDict
            ).validate_python(electrode_object["working_ion_entry"])

            for pair in electrode_object["voltage_pairs"]:
                for key in ["entries_charge", "entries_discharge"]:
                    pair[key] = [
                        TypeAdapter(TypedComputedStructureEntryDict).validate_python(
                            entry
                        )
                        for entry in pair[key]
                    ]

    return electrode_object


def electrode_object_deserializer(
    eo: dict[str, Any] | InsertionElectrode | ConversionElectrode,
) -> InsertionElectrode | ConversionElectrode:
    if isinstance(eo, dict):
        target_class: type[InsertionElectrode | ConversionElectrode]

        match eo["@class"]:
            case "InsertionElectrode":
                target_class = InsertionElectrode
                battery_type = BatteryType.insertion
                eo["working_ion_entry"] = pop_cse_empty_keys(eo["working_ion_entry"])
                for key in ["stable_entries", "unstable_entries"]:
                    eo[key] = [pop_cse_empty_keys(cse) for cse in eo[key]]

            case "ConversionElectrode":
                target_class = ConversionElectrode
                battery_type = BatteryType.conversion
                eo["working_ion_entry"] = pop_cse_empty_keys(eo["working_ion_entry"])

        if any(
            [
                isinstance(eo["working_ion_entry"].get("energy_adjustments"), _type)
                for _type in (str, bytes)
            ]
        ):
            eo = _deserialize_electrode_object_entries(eo, battery_type)
            electrode_object_energy_adjustments_serde(eo, battery_type, orjson.loads)

        eo["voltage_pairs"] = walk_voltage_pairs(eo["voltage_pairs"], battery_type)

        return target_class.from_dict(eo)

    return eo


InsertionElectrodeType = Annotated[
    InsertionElectrodeTypeVar,
    BeforeValidator(electrode_object_deserializer),
    WrapSerializer(electrode_object_serializer, return_type=dict[str, Any]),
]

ConversionElectrodeType = Annotated[
    ConversionElectrodeTypeVar,
    BeforeValidator(electrode_object_deserializer),
    WrapSerializer(electrode_object_serializer, return_type=dict[str, Any]),
]
