from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from emmet.core.utils import utcnow


class VolumetricDataDoc(BaseModel):
    """
    Volumetric data metadata for selected materials.
    """

    fs_id: str | None = Field(
        None, description="Unique object ID for the charge density data."
    )

    last_updated: datetime = Field(
        default_factory=utcnow,
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
