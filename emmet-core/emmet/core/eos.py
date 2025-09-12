from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class EOSType(TypedDict):
    V0: float
    eos_energies: list[float]
    B: float
    C: float
    E0: float


class EOSDoc(BaseModel):
    """
    Fitted equations of state and energies and volumes used for fits.
    """

    energies: list[float] | None = Field(
        None,
        description="Common energies in eV/atom that the equations of state are plotted with.",
    )

    volumes: list[float] | None = Field(
        None,
        description="Common volumes in A³/atom that the equations of state are plotted with.",
    )

    eos: EOSType | None = Field(
        None,
        description="Data for each type of equation of state.",
    )

    material_id: str | None = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )
