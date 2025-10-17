from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from emmet.core.types.enums import ValueEnum


class LegacyEOSModel(ValueEnum):
    """EOS models used to fit legacy data.

    Is overly permissive in allowing for
    spelling mistakes present in legacy data.
    """

    MIE_GRUNEISEN = "mie_gruneisen"
    PACK_EVANS_JAMES = "pack_evans_james"
    VINET = "vinet"
    TAIT = "tait"
    BIRCH_EULER = "birch_euler"
    POIRIER_TARANTOLA = "poirier_tarantola"
    BIRCH_LAGRANGE = "birch_lagrange"
    MURNAGHAN = "murnaghan"

    @classmethod
    def _missing_(cls, value):
        if value == "pourier_tarantola":
            return cls.POIRIER_TARANTOLA


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

    eos: dict[LegacyEOSModel, EOSType] | None = Field(
        None,
        description="Data for each type of equation of state.",
    )

    material_id: str | None = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )
