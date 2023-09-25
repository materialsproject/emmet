from pydantic import BaseModel, Field
from typing import Dict

try:
    from typing import Literal, Optional  # type: ignore
except ImportError:
    from typing_extensions import Literal, Optional  # type: ignore
from datetime import datetime


class GeneralStoreDoc(BaseModel):
    """
    Defines general store data
    """

    kind: Optional[Literal["newsfeed", "seminar", "banner"]] = Field(
        None, description="Type of the data."
    )

    markdown: Optional[str] = Field(None, description="Markdown data.")

    meta: Optional[Dict] = Field(None, description="Metadata.")

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=datetime.utcnow,
    )
