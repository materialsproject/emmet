from __future__ import annotations

from pydantic import BaseModel, Field

from typing import Literal

from emmet.core.types.typing import DateTimeType


class GeneralStoreDoc(BaseModel):
    """
    Defines general store data
    """

    kind: Literal["newsfeed", "seminar", "banner"] | None = Field(
        None, description="Type of the data."
    )

    markdown: str | None = Field(None, description="Markdown data.")

    meta: dict[str, str] | None = Field(None, description="Metadata.")

    last_updated: DateTimeType = Field(
        description="Timestamp for when this document was last updated",
    )
