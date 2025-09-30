"""Define schemas for charge density data."""

from __future__ import annotations

from typing import TYPE_CHECKING
from warnings import warn

from pydantic import BaseModel, Field

from emmet.core.types.typing import DateTimeType, IdentifierType
from emmet.core.vasp.models import ChgcarLike

if TYPE_CHECKING:
    from typing import Any


class VolumetricDataDoc(BaseModel):
    """
    Volumetric data metadata for selected materials.
    """

    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent update to the charge density data.",
    )

    task_id: IdentifierType | None = Field(
        None,
        description="The Materials Project ID of the calculation producing the charge density data. "
        "This comes in the form: mp-******.",
    )

    volumetric_file: str = Field(
        description="The name of the VASP file, e.g., CHGCAR, AECCAR0, etc."
    )

    volumetric_data: ChgcarLike = Field(
        description="The volumetric data from the CHGCAR-like VASP file."
    )


class ChgcarDataDoc(VolumetricDataDoc):
    """Legacy alias for backward compat."""

    def model_post_init(self, context: Any) -> None:
        """Raise deprecation warning."""
        warn(
            "ChgcarDataDoc is deprecated and will be removed in a "
            "future version of emmet-core. Please migrate to "
            "VolumetricDataDoc.",
            category=DeprecationWarning,
            stacklevel=2,
        )
