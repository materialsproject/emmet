"""Canonical, counts-only Wang-Landau sampler specification.

Vendored from phaseedge.schemas.wl_sampler_spec with imports adjusted.
"""

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from monty.json import MSONable

from emmet.builders.disorder.keys import compute_wl_key
from emmet.builders.disorder.mixture import canonical_comp_map


@dataclass(frozen=True, slots=True)
class WLSamplerSpec(MSONable):
    """Canonical, counts-only WL spec.

    - No semi-grand; no chemical potentials; no fractional composition.
    - ``composition_counts``: exact integer counts across the *entire* WL
      supercell for the replaceable sublattice species (REQUIRED).
    """

    __version__: ClassVar[str] = "3"

    ce_key: str
    bin_width: float
    steps: int

    reject_cross_sublattice_swaps: bool
    initial_comp_map: dict[str, dict[str, int]]

    step_type: str = "swap"
    check_period: int = 5_000
    update_period: int = 1
    seed: int = 0
    samples_per_bin: int = 0

    collect_cation_stats: bool = False
    production_mode: bool = False

    def __post_init__(self) -> None:
        if self.bin_width <= 0:
            raise ValueError("bin_width must be > 0.")
        if self.steps <= 0:
            raise ValueError("steps must be a positive integer.")
        if self.check_period <= 0:
            raise ValueError("check_period must be a positive integer.")
        if self.update_period <= 0:
            raise ValueError("update_period must be a positive integer.")
        if self.samples_per_bin < 0:
            raise ValueError("samples_per_bin must be >= 0.")

        object.__setattr__(
            self, "initial_comp_map", canonical_comp_map(self.initial_comp_map)
        )
        object.__setattr__(self, "collect_cation_stats", bool(self.collect_cation_stats))
        object.__setattr__(self, "production_mode", bool(self.production_mode))

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        return (
            f"{cls}("
            f"ce_key={self.ce_key!r}, "
            f"bin_width={self.bin_width}, steps={self.steps}, "
            f"initial_comp_map={self.initial_comp_map!r}, "
            f"reject_cross_sublattice_swaps={self.reject_cross_sublattice_swaps}, "
            f"step_type={self.step_type!r}, check_period={self.check_period}, "
            f"update_period={self.update_period}, seed={self.seed}, "
            f"samples_per_bin={self.samples_per_bin}, "
            f"collect_cation_stats={self.collect_cation_stats}, "
            f"production_mode={self.production_mode}"
            f")"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "@module": self.__class__.__module__,
            "@class": self.__class__.__name__,
            "@version": self.__version__,
            "ce_key": self.ce_key,
            "bin_width": self.bin_width,
            "steps": self.steps,
            "initial_comp_map": self.initial_comp_map,
            "reject_cross_sublattice_swaps": self.reject_cross_sublattice_swaps,
            "step_type": self.step_type,
            "check_period": self.check_period,
            "update_period": self.update_period,
            "seed": self.seed,
            "samples_per_bin": self.samples_per_bin,
            "collect_cation_stats": bool(self.collect_cation_stats),
            "production_mode": bool(self.production_mode),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "WLSamplerSpec":
        payload = {k: v for k, v in d.items() if not k.startswith("@")}
        return cls(
            ce_key=str(payload["ce_key"]),
            bin_width=float(payload["bin_width"]),
            steps=int(payload["steps"]),
            initial_comp_map=canonical_comp_map(payload["initial_comp_map"]),
            reject_cross_sublattice_swaps=bool(
                payload["reject_cross_sublattice_swaps"]
            ),
            step_type=str(payload.get("step_type", "swap")),
            check_period=int(payload.get("check_period", 5_000)),
            update_period=int(payload.get("update_period", 1)),
            seed=int(payload.get("seed", 0)),
            samples_per_bin=int(payload.get("samples_per_bin", 0)),
            collect_cation_stats=bool(payload["collect_cation_stats"]),
            production_mode=bool(payload["production_mode"]),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WLSamplerSpec):
            return NotImplemented
        return (
            self.ce_key == other.ce_key
            and self.bin_width == other.bin_width
            and self.steps == other.steps
            and dict(self.initial_comp_map) == dict(other.initial_comp_map)
            and self.reject_cross_sublattice_swaps
            == other.reject_cross_sublattice_swaps
            and self.step_type == other.step_type
            and self.check_period == other.check_period
            and self.update_period == other.update_period
            and self.seed == other.seed
            and self.samples_per_bin == other.samples_per_bin
            and self.collect_cation_stats == other.collect_cation_stats
            and self.production_mode == other.production_mode
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.ce_key,
                self.bin_width,
                self.steps,
                tuple(self.initial_comp_map.items()),
                self.reject_cross_sublattice_swaps,
                self.step_type,
                self.check_period,
                self.update_period,
                self.seed,
                self.samples_per_bin,
                self.collect_cation_stats,
                self.production_mode,
            )
        )

    @property
    def algo_version(self) -> str:
        return "wl-v1"

    @property
    def wl_key(self) -> str:
        """The identity key for this WL sampling setup."""
        return compute_wl_key(
            ce_key=self.ce_key,
            bin_width=self.bin_width,
            step_type=self.step_type,
            initial_comp_map=self.initial_comp_map,
            reject_cross_sublattice_swaps=self.reject_cross_sublattice_swaps,
            check_period=self.check_period,
            update_period=self.update_period,
            seed=self.seed,
            algo_version=self.algo_version,
        )
