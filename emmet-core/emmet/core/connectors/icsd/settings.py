"""Define basic settings for the ICSD API client."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IcsdClientSettings(BaseSettings):

    USERNAME: str | None = Field(None, description="ICSD username.")
    PASSWORD: str | None = Field(None, description="ICSD password.")

    MAX_RETRIES: int | None = Field(
        10, description="The maximum number of retries when querying the ICSD API."
    )

    TIMEOUT: float | None = Field(
        15.0, description="The time in seconds to wait for a query to complete."
    )

    MAX_BATCH_SIZE: int | None = Field(
        500,
        description=(
            "The maximum number of structures to retrieve "
            "during pagination of query results."
        ),
    )

    model_config = SettingsConfigDict(env_prefix="ICSD_API_")
