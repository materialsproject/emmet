from typing import List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class MessageType(Enum):
    generic = "generic"
    warning = "warning"


class MessagesDoc(BaseModel):
    """
    Defines data for user messages
    """

    title: str = Field(
        None,
        title="Title",
        description="Generic title or short summary for the message.",
    )

    body: str = Field(None, title="Body", description="Main text body of message.")

    authors: List[str] = Field(
        None,
        title="Title",
        description="Generic title or short summary for the message.",
    )

    type: MessageType = Field(
        MessageType.generic,
        title="Type",
        description="The type of the message.",
    )

    last_updated: datetime = Field(
        default_factory=datetime.utcnow,
        title="Last Updated",
        description="The last updated UTC timestamp for the message.",
    )
