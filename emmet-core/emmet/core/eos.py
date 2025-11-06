"""Define equation of state (EOS) schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, BeforeValidator
from typing import TYPE_CHECKING, Annotated

from pymatgen.analysis.eos import EOS, EOSError

from emmet.core.material import BasePropertyMetadata
from emmet.core.types.enums import ValueEnum

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from pymatgen.core import Structure


class LegacyEOSModel(ValueEnum):
    """EOS models used to fit legacy data.

    Is overly permissive in allowing for
    spelling mistakes present in legacy data.
    """

    MIE_GRUNEISEN = "mie_gruneisen"
    PACK_EVANS_JAMES = "pack_evans_james"
    BIRCH = "birch"
    VINET = "vinet"
    TAIT = "tait"
    BIRCH_EULER = "birch_euler"
    POIRIER_TARANTOLA = "poirier_tarantola"
    BIRCH_LAGRANGE = "birch_lagrange"
    MURNAGHAN = "murnaghan"
    BIRCH_MURNAGHAN = "birch_murnaghan"

    @classmethod
    def _missing_(cls, value):
        if value == "pourier_tarantola":
            return cls.POIRIER_TARANTOLA


# Subset of EOS models known to pymatgen
PYMATGEN_KNOWN_EOS_MODELS = {
    LegacyEOSModel(eos_name)
    for eos_name in ("murnaghan", "birch", "birch_murnaghan", "vinet")
}


class EOSFit(BaseModel):
    """Schematize fitted EOS data.

    The only required field is `model`.
    If no other fields are instantiated, it is assumed
    that the fit failed.
    """

    model: LegacyEOSModel = Field(description="The EOS model used to fit the data.")
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
        model: str | LegacyEOSModel,
    ):
        eos_pars: dict[str, float] = {}
        eos_model = LegacyEOSModel(model)
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


def _migrate_legacy_data(
    config: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[EOSFit] | None:
    """Migrate legacy data to new EOS schema."""
    migration = {"V0": "V0", "E0": "E0", "B": "B0", "C": "B1"}
    if isinstance(config, dict):
        config = [
            EOSFit(  # type: ignore[misc]
                **{v: config[model].get(k) for k, v in migration.items()},
                model=LegacyEOSModel(model),
            )
            for model in set(config).intersection({x.value for x in LegacyEOSModel})  # type: ignore[attr-defined]
        ]
    elif isinstance(config, list) and all(isinstance(x, dict) for x in config):
        config = [EOSFit(**x) for x in config]  # type: ignore[misc]

    return config  # type: ignore[return-value]


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

    eos: Annotated[list[EOSFit] | None, BeforeValidator(_migrate_legacy_data)] = Field(
        None,
        description="Data for each type of equation of state.",
    )

    @classmethod
    def from_ev_data(
        cls,
        structure: Structure,
        volumes: Sequence[float],
        energies: Sequence[float],
        models: list[str | LegacyEOSModel] | None = None,
    ):
        return cls.from_structure(
            meta_structure=structure,
            energies=energies,
            volumes=volumes,
            eos=[
                EOSFit.from_ev_data(volumes, energies, model)
                for model in (models or PYMATGEN_KNOWN_EOS_MODELS)  # type: ignore[union-attr]
            ],
        )
