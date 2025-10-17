from pydantic import BaseModel, Field

from emmet.core.types.enums import ValueEnum
from emmet.core.types.typing import DateTimeType


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

    last_updated: DateTimeType = Field(
        title="Last Updated",
        description="The last updated UTC timestamp for the message.",
    )
