from typing_extensions import TypedDict

from emmet.core.base import EmmetBaseModel
from emmet.core.types.pymatgen_types.alloy_adapter import AlloyPairType, AlloySystemType


class TypedBoolDict(TypedDict):
    min: bool
    max: bool


class TypedRangeDict(TypedDict):
    min: float
    max: float


class TypedSearchDict(TypedDict):
    alloying_element: list[str]
    band_gap: TypedRangeDict
    energy_above_hull: TypedRangeDict
    formation_energy_per_atom: TypedRangeDict
    formula: list[str]
    id: list[str]
    is_gap_direct: TypedBoolDict
    member_ids: list[str]
    spacegroup_intl_number: TypedRangeDict
    theoretical: TypedBoolDict
    volume_cube_root: TypedRangeDict


class AlloyPairDoc(EmmetBaseModel):
    alloy_pair: AlloyPairType

    pair_id: str

    # fields useful for building search indices
    _search: TypedSearchDict

    @classmethod
    def from_pair(cls, pair):
        return cls(alloy_pair=pair, pair_id=pair.pair_id, _search=pair.search_dict())


class AlloySystemDoc(EmmetBaseModel):
    alloy_system: AlloySystemType

    alloy_id: str

    @classmethod
    def from_pair(cls, alloy_system):
        # Too large to duplicate alloy pairs here.
        alloy_system.alloy_pairs = None  # type: ignore[assignment]
        return cls(alloy_system=alloy_system, alloy_id=alloy_system.alloy_id)
