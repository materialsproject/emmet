# from pymatgen.entries.mixing_scheme import MaterialsProjectDFTMixingScheme
# from pymatgen.entries.compatibility import MaterialsProject2020Compatibility
from typing import Annotated, TypeVar

from pydantic.functional_validators import BeforeValidator
from pymatgen.core.periodic_table import Element
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.structure_adapter import (
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


def pop_cse_empty_keys(cse: ComputedStructureEntryTypeVar):
    if isinstance(cse, dict):
        if cse.get("structure"):
            cse["structure"] = pop_empty_structure_keys(cse["structure"])
        cse["data"] = {k: v for k, v in cse["data"].items() if v}
        cse["parameters"] = {k: v for k, v in cse["parameters"].items() if v}

    return cse


AnnotatedComputedStructureEntry = Annotated[
    ComputedStructureEntryTypeVar, BeforeValidator(pop_cse_empty_keys)
]
