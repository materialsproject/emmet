from typing import TypeVar

from pymatgen.entries.mixing_scheme import MaterialsProjectDFTMixingScheme
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.compatibility_adapter import (
    TypedCompatibilityDict,
    TypedMaterialsProject2020CompatibilityAdapterDict,
)
from emmet.core.serialization_adapters.structure_matcher_adapter import (
    TypedStructureMatcherDict,
)

TypedMaterialsProjectDFTMixingSchemeDict = TypedDict(
    "TypedMaterialsProjectDFTMixingSchemeDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "structure_matcher": TypedStructureMatcherDict,
        "run_type_1": str,
        "run_type_2": str,
        "compat_1": TypedMaterialsProject2020CompatibilityAdapterDict,
        "compat_2": TypedCompatibilityDict,
        "fuzzy_matching": bool,
        "check_potcar": bool,
    },
)

MaterialsProjectDFTMixingSchemeTypeVar = TypeVar(
    "MaterialsProjectDFTMixingSchemeTypeVar",
    MaterialsProjectDFTMixingScheme,
    TypedMaterialsProjectDFTMixingSchemeDict,
)
