from pydantic import Field

from emmet.core.material import PropertyOrigin
from emmet.core.mpid import MPID, MPculeID


class MolPropertyOrigin(PropertyOrigin):
    """Provenance for molecular properties, uses legacy MPID."""

    task_id: MPID | MPculeID = Field(
        ..., description="The calculation ID this property comes from."
    )
