"""Define equation of state (EOS) schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import TYPE_CHECKING

from pymatgen.analysis.eos import EOS, EOSError

from emmet.core.material import BasePropertyMetadata
from emmet.core.types.enums import ValueEnum

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pymatgen.core import Structure


class EOSModel(ValueEnum):
    """Names of EOS models used in production."""

    MURNAGHAN = "murnaghan"
    BIRCH = "birch"
    BIRCH_MURNAGHAN = "birch_murnaghan"
    POUIER_TARANTOLA = "pourier_tarantola"
    UBER = "vinet"  # yes that's the actual name for it


class EOSFit(BaseModel):
    """Schematize fitted EOS data.

    The only required field is `model`.
    If no other fields are instantiated, it is assumed
    that the fit failed.
    """

    model: EOSModel = Field(description="The EOS model used to fit the data.")
    V0: float | None = Field(None, description="The equilibrium volume in Å³.")
    B0: float | None = Field(None, description="The equilibrium bulk modulus, in GPa.")
    B1: float | None = Field(
        None,
        description="The pressure derivative of the bulk modulus at V0, dimensionless.",
    )
    E0: float | None = Field(None, description="The equilibrium energy, in eV.")
    R2: float | None = Field(
        None, description="The fit R2 (coefficient of determination), dimensionless."
    )

    @classmethod
    def from_ev_data(
        cls,
        volumes: Sequence[float],
        energies: Sequence[float],
        model: str | EOSModel,
    ):
        eos_pars: dict[str, float] = {}
        eos_model = EOSModel(model)
        try:
            eos = EOS(eos_name=eos_model.value).fit(volumes, energies)
            eos_pars.update({k.upper(): eos.results[k] for k in ("e0", "v0", "b1")})
            eos_pars["B0"] = float(eos.b0_GPa)

            sum_res_sq = ((eos.energies - eos.func(eos.volumes)) ** 2).sum()
            sum_tot_sq = ((eos.energies - eos.energies.mean()) ** 2).sum()
            eos_pars["R2"] = 1.0 - sum_res_sq / sum_tot_sq

        except EOSError:
            pass
        return cls(model=eos_model, **eos_pars)


class EOSDoc(BasePropertyMetadata):
    """Fitted equations of state, and energy-volume fit data."""

    energies: list[float] | None = Field(
        None,
        description="Energies in eV that the equations of state are plotted with.",
    )

    volumes: list[float] | None = Field(
        None,
        description="Volumes in A³ that the equations of state are plotted with.",
    )

    eos: list[EOSFit] | None = Field(
        None,
        description="Data for each type of equation of state.",
    )

    @classmethod
    def from_ev_data(
        cls,
        structure: Structure,
        volumes: Sequence[float],
        energies: Sequence[float],
        models: list[str | EOSModel] | None = None,
    ):
        return cls.from_structure(
            meta_structure=structure,
            energies=energies,
            volumes=volumes,
            eos=[
                EOSFit.from_ev_data(volumes, energies, model)
                for model in (models or EOSModel)  # type: ignore[union-attr]
            ],
        )
