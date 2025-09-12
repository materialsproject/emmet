from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.entries.mixing_scheme import MaterialsProjectDFTMixingScheme
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.compatibility_adapter import (
    TypedCompatibilityDict,
    TypedMaterialsProject2020CompatibilityAdapterDict,
)
from emmet.core.types.pymatgen_types.structure_matcher_adapter import (
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

MaterialsProjectDFTMixingSchemeType = Annotated[
    MaterialsProjectDFTMixingSchemeTypeVar,
    BeforeValidator(
        lambda x: (
            MaterialsProjectDFTMixingScheme.from_dict(x) if isinstance(x, dict) else x
        )
    ),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(),
        return_type=TypedMaterialsProjectDFTMixingSchemeDict,
    ),
]
