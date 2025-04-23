from pydantic import BaseModel, Field

from emmet.core.typing import TypedUserSettingsDict


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
