from datetime import datetime

import pymatgen.entries.computed_entries
from pydantic import RootModel
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Element
from pymatgen.entries.compatibility import MaterialsProject2020Compatibility
from pymatgen.entries.mixing_scheme import MaterialsProjectDFTMixingScheme
from typing_extensions import TypedDict

from emmet.core.vasp.calculation import PotcarSpec

TypedEnergyAdjustmentDict = TypedDict(
    "TypedEnergyAdjustmentDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "value": float,
        "uncertainty": float,
        "name": str,
        "cls": MaterialsProject2020Compatibility | MaterialsProjectDFTMixingScheme,
        "description": str,
    },
)

TypedCompositionEnergyAdjustmentDict = TypedDict(
    "TypedCompositionEnergyAdjustmentDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "adj_per_atom": float,
        "n_atoms": int,
        "uncertainty_per_atom": float,
        "name": str,
        "cls": MaterialsProject2020Compatibility | MaterialsProjectDFTMixingScheme,
        "description": str,
    },
)

TypedTemperatureEnergyAdjustmentDict = TypedDict(
    "TypedTemperatureEnergyAdjustmentDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "adj_per_deg": float,
        "temp": float,
        "n_atoms": int,
        "uncertainty_per_deg": float,
        "name": str,
        "cls": MaterialsProject2020Compatibility | MaterialsProjectDFTMixingScheme,
        "description": str,
    },
)


class TypedCEDataDict(TypedDict):
    oxide_type: str
    aspherical: str
    last_updated: datetime
    task_id: str
    material_id: str
    oxidation_states: dict[Element, float]
    license: str
    run_type: str


class TypedCEParameterDict(TypedDict):
    potcar_spec: PotcarSpec
    run_type: str
    is_hubbard: bool
    hubbards: dict[str, float]


TypedComputedEntryDict = TypedDict(
    "TypedComputedEntryDict",
    {
        "@module": str,
        "@class": str,
        "energy": float,
        "composition": dict[Element, float],
        "entry_id": str,
        "correction": float,
        "energy_adjustments": list[
            TypedCompositionEnergyAdjustmentDict
            | TypedEnergyAdjustmentDict
            | TypedTemperatureEnergyAdjustmentDict
        ],
        "parameters": TypedCEParameterDict,
        "data": TypedCEDataDict,
    },
)


class TypedComputedStructureEntryDict(TypedComputedEntryDict):
    structure: Structure


class EnergyAdjustmentAdatper(RootModel):
    root: TypedEnergyAdjustmentDict


class ConstantEnergyAdjustmentAdatper(EnergyAdjustmentAdatper):
    pass


class ManualEnergyAdjustmentAdatper(EnergyAdjustmentAdatper):
    pass


class CompositionEnergyAdjustmentAdatper(RootModel):
    root: TypedCompositionEnergyAdjustmentDict


class TemperatureEnergyAdjustmentAdatper(RootModel):
    root: TypedTemperatureEnergyAdjustmentDict


class ComputedEntryAdapter(RootModel):
    root: TypedComputedEntryDict


class ComputedStructureEntryAdapter(RootModel):
    root: TypedComputedStructureEntryDict


pymatgen.entries.computed_entries.EnergyAdjustment.__pydantic_model__ = (
    EnergyAdjustmentAdatper
)
pymatgen.entries.computed_entries.ConstantEnergyAdjustment.__pydantic_model__ = (
    ConstantEnergyAdjustmentAdatper
)
pymatgen.entries.computed_entries.ManualEnergyAdjustment.__pydantic_model__ = (
    ManualEnergyAdjustmentAdatper
)
pymatgen.entries.computed_entries.CompositionEnergyAdjustment.__pydantic_model__ = (
    CompositionEnergyAdjustmentAdatper
)
pymatgen.entries.computed_entries.TemperatureEnergyAdjustment.__pydantic_model__ = (
    TemperatureEnergyAdjustmentAdatper
)
pymatgen.entries.computed_entries.ComputedEntry.__pydantic_model__ = (
    ComputedEntryAdapter
)
pymatgen.entries.computed_entries.ComputedStructureEntry.__pydantic_model__ = (
    ComputedStructureEntryAdapter
)
