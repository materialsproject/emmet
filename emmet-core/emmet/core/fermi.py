from typing import List, Optional
from datetime import datetime
from monty.json import MontyDecoder
from pydantic import field_validator, BaseModel, Field


class FermiDoc(BaseModel):
    """
    Fermi surfaces.
    """

    fermi_surfaces: Optional[List[dict]] = Field(
        None,
        description="List of IFermi FermiSurface objects.",
    )

    surface_types: Optional[List[str]] = Field(
        None,
        description="Type of each fermi surface in the fermi_surfaces list.\
            Is either CBM or VBM for semiconductors, or fermi_surface for metals.",
    )

    task_id: Optional[str] = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )

    last_updated: Optional[datetime] = Field(
        None,
        description="Timestamp for the most recent calculation for this fermi surface document.",
    )

    # Make sure that the datetime field is properly formatted
    @field_validator("last_updated", mode="before")
    @classmethod
    def last_updated_dict_ok(cls, v):
        return MontyDecoder().process_decoded(v)
