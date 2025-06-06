from typing import Annotated, TypeVar

import pymatgen.io.vasp.inputs
from pydantic.functional_validators import BeforeValidator
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)

TypedPoscarDict = TypedDict(
    "TypedPoscarDict",
    {
        "@module": str,
        "@class": str,
        "structure": TypedStructureDict,
        "true_names": bool,
        "selective_dynamics": list[list[bool]],
        "velocities": list[list[float]],
        "predictor_corrector": list[list[float]],
        "comment": str,
    },
)


PoscarTypeVar = TypeVar(
    "PoscarTypeVar", pymatgen.io.vasp.inputs.Poscar, TypedPoscarDict
)


def pop_poscar_empty_structure_keys(poscar: PoscarTypeVar):
    if isinstance(poscar, dict):
        clean_structure = pop_empty_structure_keys(poscar["structure"])
        poscar["structure"] = clean_structure

    return poscar


AnnotatedPoscar = Annotated[
    PoscarTypeVar, BeforeValidator(pop_poscar_empty_structure_keys)
]
