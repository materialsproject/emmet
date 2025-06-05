from typing import Annotated, TypeVar

import pymatgen.apps.battery.conversion_battery
import pymatgen.apps.battery.insertion_battery
from pydantic import BeforeValidator, RootModel
from pymatgen.analysis.reaction_calculator import BalancedReaction
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.computed_entries_adapter import (
    pop_cse_empty_keys,
)

BaseVoltagePairDict = TypedDict(
    "BaseVoltagePairDict",
    {
        # "@module": str,
        # "@class": str,
        # "@version": str,
        "voltage": float,
        "frac_charge": float,
        "frac_discharge": float,
        "framework_formula": str,
        "mAh": float,
        "mass_charge": float,
        "mass_discharge": float,
        "vol_charge": float,
        "vol_discharge": float,
    },
)

BaseInsertionVoltagePairDict = TypedDict(
    "BaseInsertionVoltagePairDict",
    {
        **BaseVoltagePairDict.__annotations__,  # type: ignore[misc]
        "working_ion_entry": ComputedEntry,
    },
)

BaseConversionVoltagePairDict = TypedDict(
    "BaseConversionVoltagePairDict",
    {
        **BaseVoltagePairDict.__annotations__,  # type: ignore[misc]
        "working_ion_entry": ComputedStructureEntry,
    },
)


class TypedInsertionVoltagePairDict(BaseInsertionVoltagePairDict):
    entry_charge: ComputedStructureEntry
    entry_discharge: ComputedStructureEntry


class TypedConversionVoltagePairDict(BaseConversionVoltagePairDict):
    entries_charge: list[ComputedStructureEntry]
    entries_discharge: list[ComputedStructureEntry]
    rxn: BalancedReaction


TypedInsertionElectrodeDict = TypedDict(
    "TypedInsertionElectrodeDict",
    {
        # "@module": str,
        # "@class": str,
        # "@version": str,
        "framework_formula": str,
        "stable_entries": list[ComputedStructureEntry],
        "unstable_entries": list[ComputedStructureEntry],
        "voltage_pairs": list[TypedInsertionVoltagePairDict],
        "working_ion_entry": ComputedEntry,
    },
)

TypedConversionElectrodeDict = TypedDict(
    "TypedConversionElectrodeDict",
    {
        # "@module": str,
        # "@class": str,
        # "@version": str,
        "framework_formula": str,
        "initial_comp_formula": str,
        "voltage_pairs": list[TypedConversionVoltagePairDict],
        "working_ion_entry": ComputedStructureEntry,
    },
)


class InsertionVoltagePairAdapter(RootModel):
    root: TypedInsertionVoltagePairDict


class InsertionElectrodeAdapter(RootModel):
    root: TypedInsertionElectrodeDict


class ConversionElectrodeAdapter(RootModel):
    root: TypedConversionElectrodeDict


setattr(
    pymatgen.apps.battery.insertion_battery.InsertionVoltagePair,
    "__type_adapter__",
    InsertionVoltagePairAdapter,
)
setattr(
    pymatgen.apps.battery.insertion_battery.InsertionElectrode,
    "__type_adapter__",
    InsertionElectrodeAdapter,
)
setattr(
    pymatgen.apps.battery.conversion_battery.ConversionElectrode,
    "__type_adapter__",
    ConversionElectrodeAdapter,
)

InsertionElectrodeTypeVar = TypeVar(
    "InsertionElectrodeTypeVar",
    pymatgen.apps.battery.insertion_battery.InsertionElectrode,
    dict,
)


def walk_ie_voltage_pairs(voltage_pairs):
    for pair in voltage_pairs:
        pair["entry_charge"] = pop_cse_empty_keys(pair["entry_charge"])
        pair["entry_discharge"] = pop_cse_empty_keys(pair["entry_discharge"])
        pair["working_ion_entry"] = pop_cse_empty_keys(pair["working_ion_entry"])

    return voltage_pairs


def pop_insertion_electrode_empty_keys(ie: InsertionElectrodeTypeVar):
    if isinstance(ie, dict):
        ie["working_ion_entry"] = pop_cse_empty_keys(ie["working_ion_entry"])
        ie["stable_entries"] = [pop_cse_empty_keys(cse) for cse in ie["stable_entries"]]
        ie["unstable_entries"] = [
            pop_cse_empty_keys(cse) for cse in ie["unstable_entries"]
        ]
        ie["voltage_pairs"] = walk_ie_voltage_pairs(ie["voltage_pairs"])

    return ie


AnnotatedInsertionElectrode = Annotated[
    InsertionElectrodeTypeVar, BeforeValidator(pop_insertion_electrode_empty_keys)
]

ConversionElectrodeTypeVar = TypeVar(
    "ConversionElectrodeTypeVar",
    pymatgen.apps.battery.conversion_battery.ConversionElectrode,
    dict,
)


def walk_ce_voltage_pairs(voltage_pairs):
    for pair in voltage_pairs:
        pair["entries_charge"] = [
            pop_cse_empty_keys(cse) for cse in pair["entries_charge"]
        ]
        pair["entries_discharge"] = [
            pop_cse_empty_keys(cse) for cse in pair["entries_discharge"]
        ]
        pair["working_ion_entry"] = pop_cse_empty_keys(pair["working_ion_entry"])

    return voltage_pairs


def pop_conversion_electrode_empty_keys(ce: ConversionElectrodeTypeVar):
    if isinstance(ce, dict):
        ce["working_ion_entry"] = pop_cse_empty_keys(ce["working_ion_entry"])
        ce["voltage_pairs"] = walk_ce_voltage_pairs(ce["voltage_pairs"])

    return ce


AnnotatedConversionElectrode = Annotated[
    ConversionElectrodeTypeVar, BeforeValidator(pop_conversion_electrode_empty_keys)
]
