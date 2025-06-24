from typing import Annotated, TypeVar

from pydantic import BeforeValidator
from pymatgen.analysis.defects.core import Defect
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.sites_adapter import MSONableTypedSiteDict
from emmet.core.serialization_adapters.structure_adapter import (
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
        clean_structure = pop_empty_structure_keys(defect["structure"])
        defect["structure"] = clean_structure

    return defect


AnnotatedDefect = Annotated[
    DefectTypeVar, BeforeValidator(pop_defect_empty_structure_fields)
]
