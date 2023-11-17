from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EOSDoc(BaseModel):
    """
    Fitted equations of state and energies and volumes used for fits.
    """

    energies: Optional[List[float]] = Field(
        None,
        description="Common energies in eV/atom that the equations of state are plotted with.",
    )

    volumes: Optional[List[float]] = Field(
        None,
        description="Common volumes in A³/atom that the equations of state are plotted with.",
    )

    eos: Optional[Dict] = Field(
        None,
        description="Data for each type of equation of state.",
    )

    task_id: Optional[str] = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )
