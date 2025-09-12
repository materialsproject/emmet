import json
from collections.abc import Callable
from typing import Annotated, Any, TypeVar

from pydantic import BeforeValidator, WrapSerializer
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
    TypedComputedEntryDict,
    TypedComputedStructureEntryDict,
    pop_cse_empty_keys,
)


class BaseVoltagePairDict(TypedDict):
    voltage: float
    frac_charge: float
    frac_discharge: float
    framework_formula: str
    mAh: float
    mass_charge: float
    mass_discharge: float
    vol_charge: float
    vol_discharge: float


class BaseInsertionVoltagePairDict(BaseVoltagePairDict):
    working_ion_entry: TypedComputedEntryDict


class BaseConversionVoltagePairDict(BaseVoltagePairDict):
    working_ion_entry: TypedComputedStructureEntryDict


class TypedInsertionVoltagePairDict(BaseInsertionVoltagePairDict):
    entry_charge: TypedComputedStructureEntryDict
    entry_discharge: TypedComputedStructureEntryDict


class TypedConversionVoltagePairDict(BaseConversionVoltagePairDict):
    entries_charge: list[TypedComputedStructureEntryDict]
    entries_discharge: list[TypedComputedStructureEntryDict]
    rxn: TypedBalancedReactionDict


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


InsertionElectrodeTypeVar = TypeVar(
    "InsertionElectrodeTypeVar",
    InsertionElectrode,
    TypedInsertionElectrodeDict,
)

ConversionElectrodeTypeVar = TypeVar(
    "ConversionElectrodeTypeVar",
    ConversionElectrode,
    TypedConversionElectrodeDict,
)


def walk_voltage_pairs(voltage_pairs: dict[str, Any], battery_type: BatteryType):
    match battery_type:
        case BatteryType.insertion:
            voltage_pair_cls = InsertionVoltagePair
            for pair in voltage_pairs:
                pair["entry_charge"] = pop_cse_empty_keys(pair["entry_charge"])
                pair["entry_discharge"] = pop_cse_empty_keys(pair["entry_discharge"])
                pair["working_ion_entry"] = pop_cse_empty_keys(
                    pair["working_ion_entry"]
                )
        case BatteryType.conversion:
            voltage_pair_cls = ConversionVoltagePair
            for pair in voltage_pairs:
                pair["entries_charge"] = [
                    pop_cse_empty_keys(cse) for cse in pair["entries_charge"]
                ]
                pair["entries_discharge"] = [
                    pop_cse_empty_keys(cse) for cse in pair["entries_discharge"]
                ]
                pair["working_ion_entry"] = pop_cse_empty_keys(
                    pair["working_ion_entry"]
                )

    return [voltage_pair_cls.from_dict(vp) for vp in voltage_pairs]


def electrode_object_energy_adjustments_serde(
    d: dict, battery_type: BatteryType, serde_fn: Callable
):
    d["working_ion_entry"]["energy_adjustments"] = serde_fn(
        d["working_ion_entry"]["energy_adjustments"]
    )
    match battery_type:
        case BatteryType.insertion:
            for pair in d["voltage_pairs"]:
                pair["working_ion_entry"]["energy_adjustments"] = serde_fn(
                    pair["working_ion_entry"]["energy_adjustments"]
                )
                pair["entry_charge"]["energy_adjustments"] = serde_fn(
                    pair["entry_charge"]["energy_adjustments"]
                )
                pair["entry_discharge"]["energy_adjustments"] = serde_fn(
                    pair["entry_discharge"]["energy_adjustments"]
                )
            for entry in d["stable_entries"]:
                entry["energy_adjustments"] = serde_fn(entry["energy_adjustments"])
            for entry in d["unstable_entries"]:
                entry["energy_adjustments"] = serde_fn(entry["energy_adjustments"])
        case BatteryType.conversion:
            for pair in d["voltage_pairs"]:
                pair["working_ion_entry"]["energy_adjustments"] = serde_fn(
                    pair["working_ion_entry"]["energy_adjustments"]
                )
                for charge_entry in pair["entries_charge"]:
                    charge_entry["energy_adjustments"] = serde_fn(
                        charge_entry["energy_adjustments"]
                    )
                for discharge_entry in pair["entries_discharge"]:
                    discharge_entry["energy_adjustments"] = serde_fn(
                        discharge_entry["energy_adjustments"]
                    )


def electrode_object_deserializer(
    eo: dict[str, Any] | InsertionElectrode | ConversionElectrode,
) -> InsertionElectrode:
    if isinstance(eo, dict):
        match eo["@class"]:
            case "InsertionElectrode":
                target_class = InsertionElectrode
                battery_type = BatteryType.insertion
                eo["working_ion_entry"] = pop_cse_empty_keys(eo["working_ion_entry"])
                eo["stable_entries"] = [
                    pop_cse_empty_keys(cse) for cse in eo["stable_entries"]
                ]
                eo["unstable_entries"] = [
                    pop_cse_empty_keys(cse) for cse in eo["unstable_entries"]
                ]

            case "ConversionElectrode":
                target_class = ConversionElectrode
                battery_type = BatteryType.conversion
                eo["working_ion_entry"] = pop_cse_empty_keys(eo["working_ion_entry"])

        if isinstance(eo["working_ion_entry"].get("energy_adjustments"), str):
            electrode_object_energy_adjustments_serde(eo, battery_type, json.loads)

        eo["voltage_pairs"] = walk_voltage_pairs(eo["voltage_pairs"], battery_type)

        return target_class.from_dict(eo)

    return eo


def electrode_object_serializer(electrode_object, nxt, info):
    default_serialized_object = nxt(electrode_object.as_dict(), info)

    format = info.context.get("format") if info.context else "standard"
    if format == "arrow":
        match default_serialized_object["@class"]:
            case "InsertionElectrode":
                battery_type = BatteryType.insertion
            case "ConversionElectrode":
                battery_type = BatteryType.conversion

        electrode_object_energy_adjustments_serde(
            default_serialized_object, battery_type, json.dumps
        )

    return default_serialized_object


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
