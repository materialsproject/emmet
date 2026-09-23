from typing import Annotated, Any, TypeVar, cast

from pydantic import BeforeValidator, WrapSerializer
from emmet.core.io.pymatgen import Structure, Molecule
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


def pop_empty_structure_keys(
    inp: StructureTypeVar | MoleculeTypeVar, serialize: bool = True
):
    if isinstance(inp, dict):
        raw_inp = cast(dict[str, Any], inp)
        target_cls = None
        if serialize:
            target_cls = Structure if raw_inp["@class"] == "Structure" else Molecule

        if properties := raw_inp.get("properties"):
            for prop, val in list(properties.items()):
                if val is None:
                    del properties[prop]

        for site in raw_inp["sites"]:
            if "name" in site:
                if not site["name"]:
                    del site["name"]

            if properties := site.get("properties"):
                for prop, val in list(properties.items()):
                    if val is None:
                        del properties[prop]

            for species in site.get("species") or []:
                for prop, val in list(species.items()):
                    if val is None:
                        del species[prop]

        if target_cls:
            return target_cls.from_dict(raw_inp)  # type: ignore[arg-type]

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
