from pydantic import BaseModel, ConfigDict, Field

from emmet.core.types.typing import DateTimeType


class VolumetricDataDoc(BaseModel):
    """
    Volumetric data metadata for selected materials.
    """

    fs_id: str | None = Field(
        None, description="Unique object ID for the charge density data."
    )

    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent update to the charge density data.",
    )

    task_id: str | None = Field(
        None,
        description="The Materials Project ID of the calculation producing the charge density data. "
        "This comes in the form: mp-******.",
    )

    model_config = ConfigDict(extra="allow")


class ChgcarDataDoc(VolumetricDataDoc):
    """
    Electron charge density metadata for selected materials.
    """
