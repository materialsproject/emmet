import pymatgen.apps.battery.conversion_battery
import pymatgen.apps.battery.insertion_battery
from pydantic import RootModel
from pymatgen.analysis.reaction_calculator import BalancedReaction
from pymatgen.entries.computed_entries import ComputedStructureEntry
from typing_extensions import TypedDict

BaseVoltagePairDict = TypedDict(
    "BaseVoltagePairDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "voltage": float,
        "frac_charge": float,
        "frac_discharge": float,
        "framework_formula": str,
        "mAh": float,
        "mass_charge": float,
        "mass_discharge": float,
        "vol_charge": float,
        "vol_discharge": float,
        "working_ion_entry": ComputedStructureEntry,
    },
)


class TypedInsertionVoltagePairDict(BaseVoltagePairDict):
    entry_charge: ComputedStructureEntry
    entry_discharge: ComputedStructureEntry


class TypedConversionVoltagePairDict(BaseVoltagePairDict):
    entries_charge: list[ComputedStructureEntry]
    entries_discharge: list[ComputedStructureEntry]
    rxn: BalancedReaction


TypedInsertionElectrodeDict = TypedDict(
    "TypedInsertionElectrodeDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "framework_formula": str,
        "stable_entries": list[ComputedStructureEntry],
        "unstable_entries": list[ComputedStructureEntry],
        "voltage_pairs": list[TypedInsertionVoltagePairDict],
        "working_ion_entry": ComputedStructureEntry,
    },
)

TypedConversionElectrodeDict = TypedDict(
    "TypedConversionElectrodeDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
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
