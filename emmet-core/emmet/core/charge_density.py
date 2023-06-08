from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datetime import datetime


class ChgcarDataDoc(BaseModel):
    """Electron charge density metadata for selected materials."""

    fs_id: str = Field(
        None, description="Unique object ID for the charge density data."
    )

    last_updated: datetime = Field(
        None,
        description="Timestamp for the most recent update to the charge density data.",
    )

    task_id: str = Field(
        None,
        description="The Materials Project ID of the calculation producing the charge density data. "
        "This comes in the form: mp-******.",
    )

    class Config:
        extra = "allow"
