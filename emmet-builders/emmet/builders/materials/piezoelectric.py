
from pydantic import BaseModel, Field

from emmet.core.math import Vector6D
from emmet.core.polar import PiezoelectricDoc
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.typing import NullableDateTimeType, IdentifierType

CENTROSYMMETRIC_SPACE_GROUPS = [
    "-1",
    "2/m",
    "mmm",
    "4/m",
    "4/mmm",
    "-3",
    "-3m",
    "6/m",
    "6/mmm",
    "m-3",
    "m-3m",
]


PIEZO_TENSOR_TYPE = tuple[Vector6D,Vector6D,Vector6D]

class PiezoBuilderInput(BaseModel):

    structure : StructureType
    material_id : IdentifierType
    task_id : IdentifierType
    nkpoints : int
    piezo_static : PIEZO_TENSOR_TYPE
    piezo_ionic : PIEZO_TENSOR_TYPE
    is_hubbard : int
    task_last_updated : NullableDateTimeType

def build_piezo_docs(piezo_input : list[PiezoBuilderInput]) -> list[PiezoelectricDoc]:
    return