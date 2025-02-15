import pymatgen.core.structure
from pydantic import RootModel
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.properties import TypedAggregateProperitesDict
from emmet.core.serialization_adapters.sites_adapter import TypedSiteDict


class TypedLattice(TypedDict):
    matrix: list[list[float, float, float]]


TypedMoleculeDict = TypedDict(
    "TypedMoleculeDict",
    {
        "@module": str,
        "@class": str,
        "charge": float,
        "spin_multiplicity": int,
        "sites": list[TypedSiteDict],
        "properties": TypedAggregateProperitesDict,
    },
)


class MoleculeAdapter(RootModel):
    root: TypedMoleculeDict


pymatgen.core.structure.Molecule.__pydantic_model__ = MoleculeAdapter
