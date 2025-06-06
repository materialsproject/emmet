from typing import TypeAlias

from emmet.core import ARROW_COMPATIBLE
from emmet.core.base import EmmetBaseModel
from emmet.core.typing import TypedSearchDict

try:
    from pymatgen.analysis.alloys.core import AlloyPair, AlloySystem
except ImportError:
    raise ImportError(
        "Install pymatgen-analysis-alloys to use AlloyPairDoc or AlloySystemDoc"
    )


if ARROW_COMPATIBLE:
    from emmet.core.serialization_adapters.alloy_adapter import (
        AnnotatedAlloyPair,
        AnnotatedAlloySystem,
    )


AlloyPairType: TypeAlias = AnnotatedAlloyPair if ARROW_COMPATIBLE else AlloyPair
AlloySystemType: TypeAlias = AnnotatedAlloySystem if ARROW_COMPATIBLE else AlloySystem


class AlloyPairDoc(EmmetBaseModel):
    alloy_pair: AlloyPairType

    pair_id: str

    # fields useful for building search indices
    _search: TypedSearchDict

    @classmethod
    def from_pair(cls, pair: AlloyPair):
        return cls(alloy_pair=pair, pair_id=pair.pair_id, _search=pair.search_dict())


class AlloySystemDoc(EmmetBaseModel):
    alloy_system: AlloySystemType

    alloy_id: str

    @classmethod
    def from_pair(cls, alloy_system: AlloySystem):
        # Too large to duplicate alloy pairs here.
        alloy_system.alloy_pairs = None  # type: ignore[assignment]
        return cls(alloy_system=alloy_system, alloy_id=alloy_system.alloy_id)
