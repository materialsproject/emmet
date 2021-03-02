"""
Settings for defaults in the build pipelines for the Materials Project
"""
from typing import Union
from pydantic.fields import Field
from emmet.core.settings import EmmetSettings


class EmmetBuildSettings(EmmetSettings):
    """
    Settings for the emmet-builder module
    The default way to modify these is to modify ~/.emmet.json or set the environment variable
    EMMET_CONFIG_FILE to point to the json with emmet settings
    """

    BUILD_TAGS: Union[str, list] = Field([], description="Tags for the build")
    DEPRECATED_TAGS: Union[str, list] = Field([], description="Tags to deprecate")
