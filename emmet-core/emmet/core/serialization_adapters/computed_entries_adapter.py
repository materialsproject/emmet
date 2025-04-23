# from pymatgen.entries.mixing_scheme import MaterialsProjectDFTMixingScheme
# from pymatgen.entries.compatibility import MaterialsProject2020Compatibility
from typing import Annotated, TypeVar

import pymatgen.entries.computed_entries
from pydantic import RootModel
from pydantic.functional_validators import BeforeValidator
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Element
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.structure_adapter import pop_empty_structure_keys
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
    oxidation_states: dict[Element, float]
    license: str
    run_type: str


class TypedCEParameterDict(TypedDict):
    potcar_spec: list[PotcarSpec]
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
    structure: Structure


# class EnergyAdjustmentAdatper(RootModel):
#     root: TypedEnergyAdjustmentDict


# class ConstantEnergyAdjustmentAdatper(EnergyAdjustmentAdatper):
#     pass


# class ManualEnergyAdjustmentAdatper(EnergyAdjustmentAdatper):
#     pass


# class CompositionEnergyAdjustmentAdatper(RootModel):
#     root: TypedCompositionEnergyAdjustmentDict


# class TemperatureEnergyAdjustmentAdatper(RootModel):
#     root: TypedTemperatureEnergyAdjustmentDict


class ComputedEntryAdapter(RootModel):
    root: TypedComputedEntryDict


class ComputedStructureEntryAdapter(RootModel):
    root: TypedComputedStructureEntryDict


# setattr(pymatgen.entries.computed_entries.EnergyAdjustment, "__type_adapter__", EnergyAdjustmentAdatper)
# setattr(pymatgen.entries.computed_entries.ConstantEnergyAdjustment, "__type_adapter__", ConstantEnergyAdjustmentAdatper)
# setattr(pymatgen.entries.computed_entries.ManualEnergyAdjustment, "__type_adapter__", ManualEnergyAdjustmentAdatper)
# setattr(pymatgen.entries.computed_entries.CompositionEnergyAdjustment, "__type_adapter__", CompositionEnergyAdjustmentAdatper)
# setattr(pymatgen.entries.computed_entries.TemperatureEnergyAdjustment, "__type_adapter__", TemperatureEnergyAdjustmentAdatper)

setattr(
    pymatgen.entries.computed_entries.ComputedEntry,
    "__type_adapter__",
    ComputedEntryAdapter,
)

setattr(
    pymatgen.entries.computed_entries.ComputedStructureEntry,
    "__type_adapter__",
    ComputedStructureEntryAdapter,
)

ComputedStructureEntryTypeVar = TypeVar(
    "ComputedStructureEntryTypeVar",
    pymatgen.entries.computed_entries.ComputedStructureEntry,
    dict,
)


def pop_cse_empty_structure_keys(cse: ComputedStructureEntryTypeVar):
    if isinstance(cse, dict):
        clean_structure = pop_empty_structure_keys(cse["structure"])
        cse["structure"] = clean_structure

    return cse


AnnotatedComputedStructureEntry = Annotated[
    ComputedStructureEntryTypeVar, BeforeValidator(pop_cse_empty_structure_keys)
]
