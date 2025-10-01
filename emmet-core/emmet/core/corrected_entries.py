"""Core definition of a CorrectedEntriesDoc Document"""

from datetime import datetime

from pydantic import Field

from emmet.core.base import EmmetBaseModel
from emmet.core.types.enums import ThermoType
from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    ComputedStructureEntryType,
)
from emmet.core.utils import type_override, utcnow
from emmet.core.vasp.calc_types.enums import RunType


@type_override({"entries": dict[ThermoType, list[ComputedStructureEntryType]]})
class CorrectedEntriesDoc(EmmetBaseModel):
    """
    A corrected entries document
    """

    property_name: str = "corrected_entries"

    chemsys: str = Field(
        ...,
        title="Chemical System",
        description="Dash-delimited string of elements in the material.",
    )

    entries: dict[RunType | ThermoType, list[ComputedStructureEntryType] | None] = (
        Field(
            ...,
            description="List of all corrected entries that are valid for the specified thermo type.",
        )
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property.",
        default_factory=utcnow,
    )
