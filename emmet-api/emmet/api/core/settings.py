from typing import Literal
from pydantic import BaseSettings, Field
from emmet.api import __file__ as root_dir
import os


class MAPISettings(BaseSettings):
    """
    Special class to store settings for MAPI
    python module
    """

    DEBUG: bool = Field(False, description="Turns on debug mode for MAPI")

    TEST_FILES: str = Field(
        os.path.join(
            os.path.dirname(os.path.abspath(root_dir)), "../../../test_files"
        ),
        description="Directory with test files",
    )

    DB_VERSION: str = Field("2021.11.10", description="Database version")

    DB_NAME_SUFFIX: Literal["blue", "green"] = Field(None, description="Database name suffix. Either blue or green.")

    TIMEOUT: int = Field(
        20, description="Number of seconds to wait for pymongo operations before raising a timeout error."
    )

    class Config:
        env_prefix = "MAPI_"
