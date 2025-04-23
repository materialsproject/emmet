import pymatgen.entries.mixing_scheme
from pydantic import RootModel
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.entries.compatibility import (
    Compatibility,
    MaterialsProject2020Compatibility,
)
from typing_extensions import TypedDict

TypedMaterialsProjectDFTMixingSchemeDict = TypedDict(
    "TypedMaterialsProjectDFTMixingSchemeDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "structure_matcher": StructureMatcher,
        "run_type_1": str,
        "run_type_2": str,
        "compat_1": MaterialsProject2020Compatibility,
        "compat_2": Compatibility,
        "fuzzy_matching": bool,
        "check_potcar": bool,
    },
)


class MaterialsProjectDFTMixingSchemeAdapter(RootModel):
    root: TypedMaterialsProjectDFTMixingSchemeDict


setattr(
    pymatgen.entries.mixing_scheme.MaterialsProjectDFTMixingScheme,
    "__type_adapter__",
    MaterialsProjectDFTMixingSchemeAdapter,
)
