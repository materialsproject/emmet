from __future__ import annotations

from pydantic import BaseModel, Field

try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing import Literal  # type: ignore
from datetime import datetime


class GeneralStoreDoc(BaseModel):
    """Defines general store data."""

    kind: Literal["newsfeed", "seminar", "banner"] = Field(
        None, description="Type of the data."
    )

    markdown: str = Field(None, description="Markdown data.")

    meta: dict = Field(None, description="Metadata.")

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=datetime.utcnow,
    )
