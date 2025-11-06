from pydantic import BaseModel, Field

from emmet.core.types.typing import DateTimeType
from emmet.core.utils import arrow_incompatible


@arrow_incompatible
class FermiDoc(BaseModel):
    """
    Fermi surfaces.
    """

    fermi_surfaces: list[dict] | None = Field(
        None,
        description="List of IFermi FermiSurface objects.",
    )

    surface_types: list[str] | None = Field(
        None,
        description="Type of each fermi surface in the fermi_surfaces list.\
            Is either CBM or VBM for semiconductors, or fermi_surface for metals.",
    )

    material_id: str | None = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )

    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent calculation for this fermi surface document.",
    )
