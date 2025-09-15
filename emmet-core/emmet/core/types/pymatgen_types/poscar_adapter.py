from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.io.vasp.inputs import Poscar
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.structure_adapter import (
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


PoscarTypeVar = TypeVar("PoscarTypeVar", Poscar, TypedPoscarDict)


def pop_poscar_empty_structure_keys(poscar: PoscarTypeVar):
    if isinstance(poscar, dict):
        clean_structure = pop_empty_structure_keys(poscar["structure"])
        poscar["structure"] = clean_structure

        return Poscar.from_dict(poscar)  # type: ignore[arg-type]

    return poscar


PoscarType = Annotated[
    PoscarTypeVar,
    BeforeValidator(pop_poscar_empty_structure_keys),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedPoscarDict),
]
