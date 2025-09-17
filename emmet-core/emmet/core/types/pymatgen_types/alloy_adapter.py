from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.core import Element
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)

try:
    from pymatgen.analysis.alloys.core import AlloyMember, AlloyPair, AlloySystem
except ImportError:
    raise ImportError(
        "Install pymatgen-analysis-alloys to use AlloyPairDoc or AlloySystemDoc"
    )


class TypedSupportedPropertiesDict(TypedDict):
    energy_above_hull: float
    formation_energy_per_atom: float
    band_gap: float
    is_gap_direct: bool
    m_n: float
    m_p: float
    theoretical: bool
    is_metal: bool


class TypedAlloyMemberDict(TypedDict):
    id_: str
    db: str
    composition: dict[Element, float]
    x: float
    is_ordered: bool


TypedAlloyPairDict = TypedDict(
    "TypedAlloyPairDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "formula_a": str,
        "formula_b": str,
        "structure_a": TypedStructureDict,
        "structure_b": TypedStructureDict,
        "id_a": str,
        "id_b": str,
        "chemsys": str,
        "alloying_element_a": str,
        "alloying_element_b": str,
        "alloying_species_a": list[str],
        "alloying_species_b": list[str],
        "observer_elements": list[str],
        "observer_species": list[str],
        "anions_a": list[str],
        "anions_b": list[str],
        "cations_a": list[str],
        "cations_b": list[str],
        "lattice_parameters_a": list[float],
        "lattice_parameters_b": list[float],
        "volume_cube_root_a": float,
        "volume_cube_root_b": float,
        "properties_a": TypedSupportedPropertiesDict,
        "properties_b": TypedSupportedPropertiesDict,
        "spacegroup_intl_number_a": int,
        "spacegroup_intl_number_b": int,
        "pair_id": str,
        "pair_formula": str,
        "alloy_oxidation_state": int,
        "isoelectronic": bool,
        "anonymous_formula": str,
        "nelements": int,
        "members": list[TypedAlloyMemberDict],
    },
)

TypedAlloySystemDict = TypedDict(
    "TypedAlloySystemDict",
    {
        "@class": str,
        "@module": str,
        "@version": str,
        "alloy_id": str,
        "alloy_pairs": list[TypedAlloyPairDict],
        "chemsys": str,
        "chemsys_size": int,
        "has_members": bool,
        "members": list[TypedAlloyMemberDict],
        "additional_members": list[TypedAlloyMemberDict],
        "n_pairs": int,
        "ids": list[str],
        "pair_ids": list[str],
    },
)


AlloyMemberTypeVar = TypeVar("AlloyMemberTypeVar", AlloyMember, TypedAlloyMemberDict)
AlloyPairTypeVar = TypeVar("AlloyPairTypeVar", AlloyPair, TypedAlloyPairDict)
AlloySystemTypeVar = TypeVar("AlloySystemTypeVar", AlloySystem, TypedAlloySystemDict)


def pop_empty_alloy_pair_structure_keys(alloy_pair: AlloyPairTypeVar):
    if isinstance(alloy_pair, dict):
        for key in ["structure_a", "structure_b"]:
            alloy_pair[key] = pop_empty_structure_keys(alloy_pair[key])  # type: ignore[literal-required]

    return alloy_pair


def pop_empty_alloy_system_structure_keys(alloy_system: AlloySystemTypeVar):
    if isinstance(alloy_system, dict):
        alloy_system["alloy_pairs"] = [
            pop_empty_alloy_pair_structure_keys(alloy_pair)
            for alloy_pair in alloy_system["alloy_pairs"]
        ]

    return alloy_system


AlloyPairType = Annotated[
    AlloyPairTypeVar,
    BeforeValidator(pop_empty_alloy_pair_structure_keys),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedAlloyPairDict),
]
AlloySystemType = Annotated[
    AlloySystemTypeVar,
    BeforeValidator(pop_empty_alloy_system_structure_keys),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedAlloySystemDict),
]
