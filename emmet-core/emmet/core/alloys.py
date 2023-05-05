from emmet.core.base import EmmetBaseModel
from typing import Dict

try:
    from pymatgen.analysis.alloys.core import (
        AlloyPair,
        AlloySystem,
    )
except ImportError:
    raise ImportError("Install pymatgen-analysis-alloys to use AlloyPairDoc or AlloySystemDoc")


class AlloyPairDoc(EmmetBaseModel):

    alloy_pair: AlloyPair

    pair_id: str

    # fields useful for building search indices
    _search: Dict

    @classmethod
    def from_pair(cls, pair: AlloyPair):
        return cls(alloy_pair=pair, pair_id=pair.pair_id, _search=pair.search_dict())


class AlloySystemDoc(EmmetBaseModel):

    alloy_system: AlloySystem

    alloy_id: str

    @classmethod
    def from_pair(cls, alloy_system: AlloySystem):
        # Too large to duplicate alloy pairs here.
        alloy_system.alloy_pairs = None
        return cls(alloy_system=alloy_system, alloy_id=alloy_system.alloy_id)
