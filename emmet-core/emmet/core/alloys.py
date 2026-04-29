from emmet.core.base import EmmetBaseModel
from emmet.core.types.pymatgen_types.alloy_adapter import (
    AlloyPairType,
    AlloySystemType,
    PairID,
)


class AlloyPairDoc(EmmetBaseModel):
    alloy_pair: AlloyPairType

    pair_id: PairID

    @classmethod
    def from_pair(cls, pair):
        return cls(alloy_pair=pair, pair_id=pair.pair_id)


class AlloySystemDoc(EmmetBaseModel):
    alloy_system: AlloySystemType

    alloy_id: str

    @classmethod
    def from_pair(cls, alloy_system):
        # Too large to duplicate alloy pairs here.
        alloy_system.alloy_pairs = None  # type: ignore[assignment]
        return cls(alloy_system=alloy_system, alloy_id=alloy_system.alloy_id)
