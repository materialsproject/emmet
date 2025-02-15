from datetime import datetime

import pymatgen.entries.computed_entries
from pydantic import RootModel
from pymatgen.core.periodic_table import Element
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.structure_adapter import TypedStructureDict
from emmet.core.vasp.calculation import PotcarSpec


class TypedCSEDataDict(TypedDict):
    oxide_type: str
    aspherical: str
    last_updated: datetime
    task_id: str
    material_id: str
    oxidation_states: dict[Element, float]
    license: str
    run_type: str


class TypedCSEParameterDict(TypedDict):
    potcar_spec: PotcarSpec
    run_type: str
    is_hubbard: bool
    hubbards: dict[str, float]


TypedComputedStructureEntryDict = TypedDict(
    "TypedComputedStructureEntryDict",
    {
        "@module": str,
        "@class": str,
        "energy": float,
        "composition": dict[Element, float],
        "entry_id": str,
        "correction": float,
        "energy_adjustments": list[float],
        "parameters": TypedCSEParameterDict,
        "data": TypedCSEDataDict,
        "structure": TypedStructureDict,
    },
)


class ComputedStructureEntryAdapter(RootModel):
    root: TypedComputedStructureEntryDict


pymatgen.entries.computed_entries.ComputedStructureEntry.__pydantic_model__ = (
    ComputedStructureEntryAdapter
)
