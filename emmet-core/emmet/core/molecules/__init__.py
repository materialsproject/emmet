from __future__ import annotations

from pydantic import BaseModel, Field

from emmet.core.mpid import MPID, MPculeID
from emmet.core.common import DateTimeType
from emmet.core.utils import utcnow


class MolPropertyOrigin(BaseModel):
    """Provenance for molecular properties, uses legacy MPID."""

    name: str = Field(..., description="The property name")

    task_id: MPID | MPculeID = Field(
        ..., description="The calculation ID this property comes from."
    )

    last_updated: DateTimeType = Field(  # type: ignore
        description="The timestamp when this calculation was last updated",
        default_factory=utcnow,
    )
