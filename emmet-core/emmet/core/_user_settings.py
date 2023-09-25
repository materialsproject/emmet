from pydantic import BaseModel, Field
from typing import Optional


class UserSettingsDoc(BaseModel):
    """
    Defines data for user settings
    """

    consumer_id: Optional[str] = Field(
        None, title="Consumer ID", description="Consumer ID for a specific user."
    )

    settings: Optional[dict] = Field(
        None,
        title="Consumer ID settings",
        description="Settings defined for a specific user.",
    )
