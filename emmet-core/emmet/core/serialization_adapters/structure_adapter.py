import pymatgen.core.structure
from pydantic import RootModel
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.lattice_adapter import TypedLatticeDict
from emmet.core.serialization_adapters.properties import TypedAggregateProperitesDict
from emmet.core.serialization_adapters.sites_adapter import TypedSiteDict

TypedStructureDict = TypedDict(
    "TypedStructureDict",
    {
        "@module": str,
        "@class": str,
        "charge": int,
        "lattice": TypedLatticeDict,
        "sites": list[TypedSiteDict],
        "properties": TypedAggregateProperitesDict,
    },
)


class StructureAdapter(RootModel):
    root: TypedStructureDict


pymatgen.core.structure.Structure.__pydantic_model__ = StructureAdapter
