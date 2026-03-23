from typing import Annotated, TypeVar

from pydantic import BaseModel, BeforeValidator, Field, TypeAdapter, WrapSerializer
from pymatgen.core import Element
from typing_extensions import NotRequired, TypedDict

from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)
from emmet.core.types.typing import MaterialIdentifierType

try:
    from pymatgen.analysis.alloys.core import AlloyMember, AlloyPair, AlloySystem
except ImportError:
    raise ImportError(
        "Install pymatgen-analysis-alloys to use AlloyPairDoc or AlloySystemDoc"
    )


class PairID(BaseModel):
    id_a: MaterialIdentifierType
    id_b: MaterialIdentifierType
    separator: str = Field(default="_")

    def __str__(self) -> str:
        """Format as a string."""
        return self.separator.join([self.id_a.string, self.id_b.value])


class TypedSupportedPropertiesDict(TypedDict):
    energy_above_hull: NotRequired[float | None]
    formation_energy_per_atom: NotRequired[float | None]
    band_gap: NotRequired[float | None]
    is_gap_direct: NotRequired[bool | None]
    m_n: NotRequired[float | None]
    m_p: NotRequired[float | None]
    theoretical: NotRequired[bool | None]
    is_metal: NotRequired[bool | None]


class TypedAlloyMemberDict(TypedDict):
    id_: NotRequired[MaterialIdentifierType | None]
    db: NotRequired[str | None]
    composition: NotRequired[dict[Element, float] | None]
    x: NotRequired[float | None]
    is_ordered: NotRequired[bool | None]


TypedAlloyPairDict = TypedDict(
    "TypedAlloyPairDict",
    {
        "@module": str,
        "@class": str,
        "@version": NotRequired[str | None],
        "formula_a": NotRequired[str | None],
        "formula_b": NotRequired[str | None],
        "structure_a": NotRequired[TypedStructureDict | None],
        "structure_b": NotRequired[TypedStructureDict | None],
        "id_a": NotRequired[MaterialIdentifierType | None],
        "id_b": NotRequired[MaterialIdentifierType | None],
        "chemsys": NotRequired[str | None],
        "alloying_element_a": NotRequired[str | None],
        "alloying_element_b": NotRequired[str | None],
        "alloying_species_a": NotRequired[str | None],
        "alloying_species_b": NotRequired[str | None],
        "observer_elements": NotRequired[list[str] | None],
        "observer_species": NotRequired[list[str] | None],
        "anions_a": NotRequired[list[str] | None],
        "anions_b": NotRequired[list[str] | None],
        "cations_a": NotRequired[list[str] | None],
        "cations_b": NotRequired[list[str] | None],
        "lattice_parameters_a": NotRequired[list[float] | None],
        "lattice_parameters_b": NotRequired[list[float] | None],
        "volume_cube_root_a": NotRequired[float | None],
        "volume_cube_root_b": NotRequired[float | None],
        "properties_a": NotRequired[TypedSupportedPropertiesDict | None],
        "properties_b": NotRequired[TypedSupportedPropertiesDict | None],
        "spacegroup_intl_number_a": NotRequired[int | None],
        "spacegroup_intl_number_b": NotRequired[int | None],
        "pair_id": NotRequired[PairID | None],
        "pair_formula": NotRequired[str | None],
        "alloy_oxidation_state": NotRequired[float | None],
        "isoelectronic": NotRequired[bool | None],
        "anonymous_formula": NotRequired[str | None],
        "nelements": NotRequired[int | None],
        "members": NotRequired[list[TypedAlloyMemberDict] | None],
    },
)

TypedAlloySystemDict = TypedDict(
    "TypedAlloySystemDict",
    {
        "@class": str,
        "@module": str,
        "@version": NotRequired[str | None],
        "alloy_id": NotRequired[str | None],
        "alloy_pairs": list[TypedAlloyPairDict],
        "chemsys": NotRequired[str | None],
        "chemsys_size": NotRequired[int | None],
        "has_members": NotRequired[bool | None],
        "members": NotRequired[list[TypedAlloyMemberDict] | None],
        "additional_members": NotRequired[list[TypedAlloyMemberDict] | None],
        "n_pairs": NotRequired[int | None],
        "ids": NotRequired[list[str] | None],
        "pair_ids": NotRequired[list[PairID] | None],
    },
)


AlloyMemberTypeVar = TypeVar("AlloyMemberTypeVar", AlloyMember, TypedAlloyMemberDict)
AlloyPairTypeVar = TypeVar("AlloyPairTypeVar", AlloyPair, TypedAlloyPairDict)
AlloySystemTypeVar = TypeVar("AlloySystemTypeVar", AlloySystem, TypedAlloySystemDict)


def pop_empty_alloy_pair_structure_keys(alloy_pair: AlloyPairTypeVar):
    if isinstance(alloy_pair, dict):
        for key in ["structure_a", "structure_b"]:
            alloy_pair[key] = pop_empty_structure_keys(alloy_pair[key], serialize=False)  # type: ignore[literal-required]

    return AlloyPair.from_dict(
        TypeAdapter(TypedAlloyPairDict).validate_python(alloy_pair)
    )


def pop_empty_alloy_system_structure_keys(alloy_system: AlloySystemTypeVar):
    if isinstance(alloy_system, dict):
        alloy_system["alloy_pairs"] = [
            pop_empty_alloy_pair_structure_keys(alloy_pair)
            for alloy_pair in alloy_system["alloy_pairs"]
        ]

    return AlloySystem.from_dict(
        TypeAdapter(TypedAlloySystemDict).validate_python(alloy_system)
    )


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
