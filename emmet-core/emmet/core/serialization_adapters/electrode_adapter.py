from typing import Annotated, TypeVar

from pydantic import BeforeValidator
from pymatgen.apps.battery.conversion_battery import ConversionElectrode
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.balanced_reaction_adapter import (
    TypedBalancedReactionDict,
)
from emmet.core.serialization_adapters.computed_entries_adapter import (
    TypedComputedEntryDict,
    TypedComputedStructureEntryDict,
    pop_cse_empty_keys,
)


# pmg .as_dict() missing:
# "@module": str,
# "@class": str,
# "@version": str,
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


# pmg .as_dict() missing:
# "@module": str,
# "@class": str,
# "@version": str,
class TypedInsertionElectrodeDict(TypedDict):
    framework_formula: str
    stable_entries: list[TypedComputedStructureEntryDict]
    unstable_entries: list[TypedComputedStructureEntryDict]
    voltage_pairs: list[TypedInsertionVoltagePairDict]
    working_ion_entry: TypedComputedEntryDict


# pmg .as_dict() missing:
# "@module": str,
# "@class": str,
# "@version": str,
class TypedConversionElectrodeDict(TypedDict):
    framework_formula: str
    initial_comp_formula: str
    voltage_pairs: list[TypedConversionVoltagePairDict]
    working_ion_entry: TypedComputedStructureEntryDict


InsertionElectrodeTypeVar = TypeVar(
    "InsertionElectrodeTypeVar",
    InsertionElectrode,
    TypedInsertionElectrodeDict,
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
    ConversionElectrode,
    TypedConversionElectrodeDict,
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
