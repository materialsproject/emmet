from typing import Annotated, TypeVar

import pymatgen.io.vasp.inputs
from pydantic import RootModel
from pydantic.functional_validators import BeforeValidator
from pymatgen.core import Structure
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.structure_adapter import pop_empty_structure_keys

TypedPoscarDict = TypedDict(
    "TypedPoscarDict",
    {
        "@module": str,
        "@class": str,
        "structure": Structure,
        "true_names": bool,
        "selective_dynamics": list[list[bool]],
        "velocities": list[list[float]],
        "predictor_corrector": list[list[float]],
        "comment": str,
    },
)


class PoscarAdapter(RootModel):
    root: TypedPoscarDict


setattr(pymatgen.io.vasp.inputs.Poscar, "__type_adapter__", PoscarAdapter)

PoscarTypeVar = TypeVar("PoscarTypeVar", pymatgen.io.vasp.inputs.Poscar, dict)


def pop_poscar_empty_structure_keys(poscar: PoscarTypeVar):
    if isinstance(poscar, dict):
        clean_structure = pop_empty_structure_keys(poscar["structure"])
        poscar["structure"] = clean_structure

    return poscar


AnnotatedPoscar = Annotated[
    PoscarTypeVar, BeforeValidator(pop_poscar_empty_structure_keys)
]
