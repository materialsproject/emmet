from datetime import datetime

from pydantic import BaseModel, Field

from emmet.core.utils import utcnow
from emmet.core.types.enums import ValueEnum


class MessageType(ValueEnum):
    generic = "generic"
    warning = "warning"


class MessagesDoc(BaseModel):
    """
    Defines data for user messages
    """

    title: str | None = Field(
        None,
        title="Title",
        description="Generic title or short summary for the message.",
    )

    body: str | None = Field(
        None, title="Body", description="Main text body of message."
    )

    authors: list[str] | None = Field(
        None,
        title="Title",
        description="Generic title or short summary for the message.",
    )

    type: MessageType = Field(  # type: ignore[assignment]
        MessageType.generic,
        title="Type",
        description="The type of the message.",
    )

    last_updated: datetime = Field(
        default_factory=utcnow,
        title="Last Updated",
        description="The last updated UTC timestamp for the message.",
    )
