import pymatgen.core.periodic_table
from pydantic import RootModel
from typing_extensions import TypedDict

MSONableTypedSpeciesDict = TypedDict(
    "MSONableTypedSpeciesDict",
    {
        "@module": str,
        "@class": str,
        "element": str,
        "oxidation_state": float,
        "spin": float,
    },
)


class TypedSpeciesDict(TypedDict):
    element: str
    oxidation_state: float
    spin: float
    occu: int


class SpeciesAdapter(RootModel):
    root: MSONableTypedSpeciesDict


setattr(pymatgen.core.sites.Species, "__type_adapter__", SpeciesAdapter)
