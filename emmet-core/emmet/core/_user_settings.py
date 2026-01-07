from pydantic import BaseModel, Field

from emmet.core.types.typing import DateTimeType


class UserSettings(BaseModel):
    """User settings assigned at sign up modal."""

    institution: str | None = None
    sector: str | None = None
    job_role: str | None = None
    is_email_subscribed: bool = False
    message_last_read: DateTimeType
    agreed_terms: bool = False


class UserSettingsDoc(BaseModel):
    """
    Defines data for user settings
    """

    consumer_id: str | None = Field(
        None, title="Consumer ID", description="Consumer ID for a specific user."
    )

    settings: UserSettings | None = Field(
        None,
        title="Consumer ID settings",
        description="Settings defined for a specific user.",
    )
