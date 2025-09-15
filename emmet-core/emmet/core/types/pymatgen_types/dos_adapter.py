from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.electronic_structure.dos import CompleteDos
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)

TypedDosDict = TypedDict(
    "TypedDosDict",
    {
        "@module": str,
        "@class": str,
        "efermi": float,
        "energies": list[float],
        "densities": dict[str, list[float]],
    },
)

TypedCompleteDosDict = TypedDict(
    "TypedCompleteDosDict",
    {
        "@module": str,
        "@class": str,
        "efermi": float,
        "structure": TypedStructureDict,
        "energies": list[float],
        "densities": dict[str, list[float]],
        "pdos": list[dict[str, dict[str, dict[str, list[float]]]]],
        "atom_dos": dict[str, TypedDosDict],
        "spd_dos": dict[str, TypedDosDict],
    },
)


CompleteDosTypeVar = TypeVar("CompleteDosTypeVar", CompleteDos, TypedCompleteDosDict)


def pop_empty_dos_keys(dos: CompleteDosTypeVar):
    if isinstance(dos, dict):
        dos["structure"] = pop_empty_structure_keys(dos["structure"])
        return CompleteDos.from_dict(dos)  # type: ignore[arg-type]

    return dos


CompleteDosType = Annotated[
    CompleteDosTypeVar,
    BeforeValidator(pop_empty_dos_keys),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedCompleteDosDict),
]
