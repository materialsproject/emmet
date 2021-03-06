"""
Settings for defaults in the build pipelines for the Materials Project
"""
from typing import List
from pydantic.fields import Field
from emmet.core.settings import EmmetSettings
from emmet.core.vasp.calc_types import TaskType


class EmmetBuildSettings(EmmetSettings):
    """
    Settings for the emmet-builder module
    The default way to modify these is to modify ~/.emmet.json or set the environment variable
    EMMET_CONFIG_FILE to point to the json with emmet settings
    """

    BUILD_TAGS: List[str] = Field(
        [], description="Tags for calculations to build materials"
    )
    EXCLUDED_TAGS: List[str] = Field(
        [],
        description="Tags to exclude from materials",
    )

    DEPRECATED_TAGS: List[str] = Field(
        [], description="Tags for calculations to deprecate"
    )

    VASP_ALLOWED_VASP_TYPES: List[TaskType] = Field(
        [t.value for t in TaskType],
        description="Allowed task_types to build materials from",
    )
