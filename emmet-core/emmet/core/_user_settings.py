from datetime import datetime

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class TypedUserSettingsDict(TypedDict):
    institution: str
    sector: str
    job_role: str
    is_email_subscribed: bool
    message_last_read: datetime
    agreed_terms: bool


class UserSettingsDoc(BaseModel):
    """
    Defines data for user settings
    """

    consumer_id: str | None = Field(
        None, title="Consumer ID", description="Consumer ID for a specific user."
    )

    settings: TypedUserSettingsDict | None = Field(
        None,
        title="Consumer ID settings",
        description="Settings defined for a specific user.",
    )
