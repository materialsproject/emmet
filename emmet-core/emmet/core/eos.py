"""Define equation of state (EOS) schemas."""

from pydantic import BaseModel, Field

from pymatgen.analysis.eos import EOS, EOSError

from emmet.core.material import BasePropertyMetadata
from emmet.core.types.enums import ValueEnum


class EOSModel(ValueEnum):
    """Names of EOS models used in production."""

    MURNAGHAN = "murnaghan"
    BIRCH = "birch"
    BIRCH_MURNAGHAN = "birch_murnaghan"
    POUIER_TARANTOLA = "pourier_tarantola"
    UBER = "vinet"  # yes that's the actual name for it


class EOSType(BaseModel):

    V0: float = Field(description="The equilibrium volume in Å³/atom.")
    B0: float = Field(description="The equilibrium bulk modulus, in GPa.")
    B1: float = Field(
        description="The pressure derivative of the bulk modulus at V0, dimensionless."
    )
    E0: float = Field(description="The equilibrium energy, in eV/atom.")
    R2: float = Field(description="The fit R2, dimensionless.")
    model: EOSModel | None = Field(
        None, description="The EOS model used to fit the data."
    )

    @classmethod
    def from_ev_data(
        cls,
        volumes: list[float],
        energies: list[float],
        model: str | EOSModel,
        num_sites: int | None = None,
    ):
        cls_config = {"model": EOSModel(model)}
        try:
            eos = EOS(eos_name=cls_config["model"].value).fit(volumes, energies)
            cls_config.update({k.upper(): eos.results[k] for k in ("e0", "v0", "b1")})
            cls_config["B0"] = (eos.b0_GPa,)
            if num_sites:
                for k in ("E0", "V0"):
                    cls_config[k] /= num_sites

            # cls_config["R2"] = 1. -

        except EOSError:
            pass
        return cls(**cls_config)


class EOSDoc(BasePropertyMetadata):
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
