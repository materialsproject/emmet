from pydantic import BaseModel, Field
from datetime import datetime
from pymatgen.io.vasp import Chgcar
from maggma.api.models import S3URLDoc


class ChgcarDataDoc(BaseModel):
    """
    Electron charge density metadata for selected materials.
    """

    fs_id: str = Field(None, description="Unique object ID for the charge density data.")

    last_updated: datetime = Field(
        None, description="Timestamp for the most recent update to the charge density data.",
    )

    task_id: str = Field(
        None,
        description="The Materials Project ID of the calculation producing the charge density data. "
        "This comes in the form: mp-******.",
    )

    class Config:
        extra = "allow"
