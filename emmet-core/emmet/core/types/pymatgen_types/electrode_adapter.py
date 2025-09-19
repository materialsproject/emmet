from collections.abc import Callable
from typing import Annotated, Any, TypeVar

import orjson
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

                pair["working_ion_entry"] = pop_cse_empty_keys(
                    pair["working_ion_entry"]
                )

    return [voltage_pair_cls.from_dict(vp) for vp in voltage_pairs]


def electrode_object_energy_adjustments_serde(
    d: dict, battery_type: BatteryType, serde_fn: Callable, ea="energy_adjustments"
):
    pair: dict[str, Any]

    d["working_ion_entry"][ea] = serde_fn(d["working_ion_entry"][ea])

    match battery_type:
        case BatteryType.insertion:
            for pair in d["voltage_pairs"]:
                for key in ["working_ion_entry", "entry_charge", "entry_discharge"]:
                    pair[key][ea] = serde_fn(pair[key][ea])

            for key in ["stable_entries", "unstable_entries"]:
                for entry in d[key]:
                    entry[ea] = serde_fn(entry[ea])

        case BatteryType.conversion:
            for pair in d["voltage_pairs"]:
                pair["working_ion_entry"][ea] = serde_fn(pair["working_ion_entry"][ea])
                for key in ["entries_charge", "entries_discharge"]:
                    for entry in pair[key]:
                        entry[ea] = serde_fn(entry[ea])


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

        if isinstance(eo["working_ion_entry"].get("energy_adjustments"), str):
            electrode_object_energy_adjustments_serde(eo, battery_type, orjson.loads)

        eo["voltage_pairs"] = walk_voltage_pairs(eo["voltage_pairs"], battery_type)

        return target_class.from_dict(eo)

    return eo


def electrode_object_serializer(electrode_object, nxt, info) -> dict[str, Any]:
    default_serialized_object = nxt(electrode_object.as_dict(), info)

    format = info.context.get("format") if info.context else None
    if format == "arrow":
        battery_type = (
            BatteryType.insertion
            if default_serialized_object["@class"] == "InsertionElectrode"
            else BatteryType.conversion
        )

        electrode_object_energy_adjustments_serde(
            default_serialized_object, battery_type, orjson.dumps
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
