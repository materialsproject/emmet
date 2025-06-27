from __future__ import annotations

from pydantic import BaseModel, Field

from emmet.core.utils import utcnow

from typing import Literal

from datetime import datetime


class GeneralStoreDoc(BaseModel):
    """
    Defines general store data
    """

    kind: Literal["newsfeed", "seminar", "banner"] | None = Field(
        None, description="Type of the data."
    )

    markdown: str | None = Field(None, description="Markdown data.")

    meta: dict | None = Field(None, description="Metadata.")

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=utcnow,
    )
