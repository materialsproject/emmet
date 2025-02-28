import pymatgen.electronic_structure.dos
from pydantic import RootModel
from pymatgen.core import Structure
from typing_extensions import TypedDict

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
        "structure": Structure,
        "energies": list[float],
        "densities": dict[str, list[float]],
        "pdos": list[dict[str, dict[str, dict[str, list[float]]]]],
        "atom_dos": dict[str, TypedDosDict],
        "spd_dos": dict[str, TypedDosDict],
    },
)


class DosAdapter(RootModel):
    root: TypedDosDict


class CompleteDosAdapter(RootModel):
    root: TypedCompleteDosDict


pymatgen.electronic_structure.dos.Dos.__pydantic_model__ = DosAdapter
pymatgen.electronic_structure.dos.CompleteDos.__pydantic_model__ = CompleteDosAdapter
