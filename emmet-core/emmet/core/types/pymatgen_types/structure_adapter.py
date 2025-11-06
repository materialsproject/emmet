from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.core import Structure
from pymatgen.core.structure import Molecule
from typing_extensions import NotRequired, TypedDict

from emmet.core.types.pymatgen_types.lattice_adapter import TypedLatticeDict
from emmet.core.types.pymatgen_types.properties import TypedAggregateProperitesDict
from emmet.core.types.pymatgen_types.sites_adapter import TypedSiteDict

TypedStructureDict = TypedDict(
    "TypedStructureDict",
    {
        "@module": str,
        "@class": str,
        "charge": NotRequired[float | None],
        "lattice": TypedLatticeDict,
        "sites": list[TypedSiteDict],
        "properties": NotRequired[TypedAggregateProperitesDict | None],
    },
)

StructureTypeVar = TypeVar("StructureTypeVar", Structure, TypedStructureDict)

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


MoleculeTypeVar = TypeVar("MoleculeTypeVar", Molecule, TypedMoleculeDict)


def pop_empty_structure_keys(inp: StructureTypeVar | MoleculeTypeVar):
    if isinstance(inp, dict):
        target_cls = Structure if inp["@class"] == "Structure" else Molecule

        if inp.get("properties"):
            for prop, val in list(inp["properties"].items()):  # type: ignore[union-attr]
                if val is None:
                    del inp["properties"][prop]  # type: ignore[union-attr]

        for site in inp["sites"]:
            if "name" in site:
                if not site["name"]:
                    del site["name"]

            if site.get("properties"):
                for prop, val in list(site["properties"].items()):
                    if val is None:
                        del site["properties"][prop]

            for species in site["species"]:
                for prop, val in list(species.items()):
                    if val is None:
                        del species[prop]

        return target_cls.from_dict(inp)  # type: ignore[arg-type]

    return inp


MoleculeType = Annotated[
    MoleculeTypeVar,
    BeforeValidator(pop_empty_structure_keys),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedMoleculeDict),
]

StructureType = Annotated[
    StructureTypeVar,
    BeforeValidator(pop_empty_structure_keys),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedStructureDict),
]
