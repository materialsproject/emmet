from typing import Annotated, TypeVar

from monty.json import MontyDecoder
from pydantic import BeforeValidator, WrapSerializer
from pymatgen.analysis.defects.core import Defect
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.sites_adapter import MSONableTypedSiteDict
from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)

TypedDefectDict = TypedDict(
    "TypedDefectDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "structure": TypedStructureDict,
        "site": MSONableTypedSiteDict,
        "multiplicity": int,
        "oxi_state": float,
        "equivalent_sites": list[MSONableTypedSiteDict],
        "symprec": float,
        "angle_tolerance": float,
        "user_changes": list[int],
    },
)

DefectTypeVar = TypeVar("DefectTypeVar", Defect, TypedDefectDict)


def pop_defect_empty_structure_fields(defect: DefectTypeVar):
    if isinstance(defect, dict):
        defect["structure"] = pop_empty_structure_keys(defect["structure"])
        return MontyDecoder().process_decoded(defect)

    return defect


DefectType = Annotated[
    DefectTypeVar,
    BeforeValidator(pop_defect_empty_structure_fields),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedDefectDict),
]
