from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

from emmet.core.common import convert_datetime
from emmet.core.mpid import MPID, MPculeID
from emmet.core.utils import utcnow

if TYPE_CHECKING:
    from typing import Any


class MolPropertyOrigin(BaseModel):
    """Provenance for molecular properties, uses legacy MPID."""

    name: str = Field(..., description="The property name")

    task_id: MPID | MPculeID = Field(
        ..., description="The calculation ID this property comes from."
    )

    last_updated: datetime = Field(  # type: ignore
        description="The timestamp when this calculation was last updated",
        default_factory=utcnow,
    )

    @field_validator("last_updated", mode="before")
    @classmethod
    def handle_datetime_and_idx(cls, v: Any) -> Any:
        if v:
            return convert_datetime(cls, v)
        return v
