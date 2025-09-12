from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.core.structure import Molecule
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.properties import TypedAggregateProperitesDict
from emmet.core.types.pymatgen_types.sites_adapter import TypedSiteDict

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


def pop_empty_molecule_keys(molecule: MoleculeTypeVar):
    if isinstance(molecule, dict):
        if molecule.get("properties"):
            for prop, val in list(molecule["properties"].items()):
                if val is None:
                    del molecule["properties"][prop]

        for site in molecule["sites"]:
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

    return molecule


MoleculeType = Annotated[
    MoleculeTypeVar,
    BeforeValidator(pop_empty_molecule_keys),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedMoleculeDict),
]
