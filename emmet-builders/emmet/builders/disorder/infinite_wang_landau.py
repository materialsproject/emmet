"""Infinite-window Wang-Landau kernel for multicanonical DOS estimation.

Vendored from phaseedge.sampling.infinite_wang_landau with imports adjusted.

This is a minimally edited copy of smol's Wang-Landau kernel that:
- Removes the fixed enthalpy window (min/max).
- Stores per-bin state sparsely in dicts, creating bins lazily as they are visited.
- Snaps bins to a global anchor at 0.0 using bin_id = floor(E / bin_size).
- Exposes the same public properties (levels/entropy/histogram/dos) but only for visited bins.
- Keeps Wang-Landau logic (flatness check, mod_factor schedule) intact.
- Can capture up to K UNIQUE occupancy samples per visited bin.
- Can optionally collect per-bin cation-count histograms per sublattice.
- Can run in "production_mode" where WL updates are frozen but statistics are collected.
"""

import hashlib
from functools import partial
from math import log
from typing import Any, Callable, Mapping

import numpy as np
from pydantic import BaseModel, Field
from smol.moca.kernel.base import ALL_MCUSHERS, MCKernel


class WLKernelState(BaseModel):
    """Builder-internal WL kernel state for checkpointing and resuming sampling."""

    version: int = Field(...)
    bin_indices: list[int] = Field(...)
    entropy: list[float] = Field(...)
    histogram: list[int] = Field(...)
    occurrences: list[int] = Field(...)
    mean_features: list[list[float]] = Field(...)
    mod_factor: float = Field(...)
    steps_counter: int = Field(...)
    current_enthalpy: float = Field(...)
    current_features: list[float] = Field(...)
    rng_state: dict[str, Any] = Field(...)
    bin_size: float = Field(...)


def _divide(x: float, m: float) -> float:
    """Use to allow Wang-Landau to be pickled."""
    return x / m


class InfiniteWangLandau(MCKernel):
    """Wang-Landau sampling kernel with an effectively unbounded enthalpy domain."""

    valid_mcushers = ALL_MCUSHERS
    valid_bias = None

    def __init__(
        self,
        ensemble,
        step_type: str,
        bin_size: float,
        *args,
        sublattice_indices: dict[str, tuple[np.ndarray, dict[int, str]]],
        reject_cross_sublattice_swaps: bool,
        flatness: float = 0.8,
        mod_factor: float = 1.0,
        check_period: int = 1000,
        update_period: int = 1,
        mod_update: float | Callable[[float], float] | None = None,
        seed: int | None = None,
        samples_per_bin: int = 0,
        collect_cation_stats: bool = False,
        production_mode: bool = False,
        **kwargs,
    ):
        if mod_factor <= 0:
            raise ValueError("mod_factor must be greater than 0.")
        if bin_size <= 0:
            raise ValueError("bin_size must be greater than 0.")

        self.flatness = float(flatness)
        self.check_period = int(check_period)
        self.update_period = int(update_period)
        self._m = float(mod_factor)
        self._bin_size = float(bin_size)
        self._mod_updates_buf: list[tuple[int, float]] = []
        self._mod_updates_buf.append((0, self._m))

        if callable(mod_update):
            self._mod_update: Callable[[float], float] = mod_update
        elif mod_update is not None:
            self._mod_update = partial(_divide, m=float(mod_update))
        else:
            self._mod_update = partial(_divide, m=2.0)

        # Sparse per-bin state
        self._entropy_d: dict[int, float] = {}
        self._histogram_d: dict[int, int] = {}
        self._occurrences_d: dict[int, int] = {}
        self._mean_features_d: dict[int, np.ndarray] = {}

        # Optional sparse capture of occupancy samples per bin (UNIQUE)
        self._samples_per_bin: int = max(0, int(samples_per_bin))
        self._bin_samples_d: dict[int, list[list[int]]] = {}
        self._bin_sample_hashes_d: dict[int, set[str]] = {}

        self._last_accepted_occupancy: np.ndarray | None = None
        self._current_enthalpy: float = np.inf
        self._current_features = np.zeros(len(ensemble.natural_parameters))
        self._nfeat = len(ensemble.natural_parameters)
        self._steps_counter = 0

        # Sublattice/species configuration
        self._collect_cation_stats = collect_cation_stats
        self._production_mode = production_mode

        self._sublattice_indices = sublattice_indices
        self._site_to_sl: dict[int, str] = {}
        for sl, (idx, _) in self._sublattice_indices.items():
            for i in np.asarray(idx, dtype=np.int32):
                self._site_to_sl[int(i)] = sl

        self._reject_cross_sublattice_swaps: bool = bool(reject_cross_sublattice_swaps)

        # Per-bin cation count histograms
        self._bin_cation_counts: dict[
            int, dict[str, dict[str, dict[int, int]]]
        ] = {}

        super().__init__(
            ensemble=ensemble, step_type=step_type, *args, seed=seed, **kwargs
        )

        if self.bias is not None:
            raise ValueError("Cannot apply bias to Wang-Landau simulation!")

        self.spec.bin_size = self._bin_size
        self.spec.flatness = self.flatness
        self.spec.check_period = self.check_period
        self.spec.update_period = self.update_period
        self.spec.samples_per_bin = self._samples_per_bin
        self.spec.collect_cation_stats = self._collect_cation_stats
        self.spec.production_mode = self._production_mode
        self.spec.reject_cross_sublattice_swaps = self._reject_cross_sublattice_swaps

        self._entropy_d.clear()
        self._histogram_d.clear()
        self._occurrences_d.clear()
        self._mean_features_d.clear()
        self._bin_samples_d.clear()
        self._bin_sample_hashes_d.clear()
        self._steps_counter = 0

    @property
    def bin_size(self) -> float:
        return self._bin_size

    def _sorted_bins(self) -> list[int]:
        return sorted([b for b, ent in self._entropy_d.items() if ent > 0])

    def _as_array(self, m: Mapping[int, float | int]) -> np.ndarray:
        bins = self._sorted_bins()
        return np.asarray([m.get(b, 0) for b in bins])

    @property
    def levels(self) -> np.ndarray:
        bins = self._sorted_bins()
        return np.asarray([self._get_bin_enthalpy(b) for b in bins], dtype=float)

    @property
    def entropy(self) -> np.ndarray:
        return self._as_array(self._entropy_d).astype(float)

    @property
    def dos(self) -> np.ndarray:
        ent = self.entropy
        return np.exp(ent - ent.min()) if ent.size else np.asarray([], dtype=float)

    @property
    def histogram(self) -> np.ndarray:
        return self._as_array(self._histogram_d).astype(int)

    @property
    def bin_indices(self) -> np.ndarray:
        return np.asarray(self._sorted_bins(), dtype=int)

    @property
    def mod_factor(self) -> float:
        return self._m

    # -------------------- helpers --------------------

    def _get_bin_id(self, e: float) -> int | float:
        if e == np.inf:
            return np.inf
        return int(np.floor(e / self._bin_size))

    def _get_bin_enthalpy(self, bin_id: int) -> float:
        return bin_id * self._bin_size

    @staticmethod
    def _hash_occupancy_int32(occ: np.ndarray) -> str:
        buf = np.asarray(occ, dtype=np.int32, order="C")
        return hashlib.sha1(buf.tobytes()).hexdigest()

    def _update_cation_stats_for_bin(self, b: int) -> None:
        if not self._collect_cation_stats:
            return
        if self._last_accepted_occupancy is None:
            return

        occ = np.asarray(self._last_accepted_occupancy, dtype=np.int32)

        if b not in self._bin_cation_counts:
            self._bin_cation_counts[b] = {}
        bin_dict = self._bin_cation_counts[b]
        for sl, (idx, code_to_elem) in self._sublattice_indices.items():
            if sl not in bin_dict:
                bin_dict[sl] = {}
            sl_dict = bin_dict[sl]

            codes, counts = np.unique(occ[idx], return_counts=True)
            zero_code_counts = [
                (code, 0) for code in code_to_elem if code not in codes
            ]
            for code, n_sites in zero_code_counts + list(zip(codes, counts)):
                elem = code_to_elem[code]
                if elem not in sl_dict:
                    sl_dict[elem] = {}
                elem_dict = sl_dict[elem]
                elem_dict[n_sites] = int(elem_dict.get(n_sites, 0) + 1)

    # -------- cross-sublattice filter helpers --------

    def _is_cross_sublattice_swap(self, step: Any) -> bool:
        if not self._site_to_sl:
            raise RuntimeError(
                "Cannot check cross-sublattice swaps without sublattice_indices."
            )
        if not step:
            return False
        [(i0, _), (i1, _)] = step
        return self._site_to_sl[i0] != self._site_to_sl[i1]

    # -------------------- MC step logic --------------------

    def _accept_step(self, occupancy: np.ndarray, step) -> np.ndarray:
        if self._reject_cross_sublattice_swaps and self._is_cross_sublattice_swap(
            step
        ):
            self.trace.accepted = np.array(False)
            return self.trace.accepted

        bin_id = self._get_bin_id(self._current_enthalpy)
        new_enthalpy = self._current_enthalpy + self.trace.delta_trace.enthalpy
        new_bin_id = self._get_bin_id(new_enthalpy)

        if not np.isfinite(new_bin_id):
            self.trace.accepted = np.array(False)
            return self.trace.accepted

        entropy = (
            float(self._entropy_d.get(int(bin_id), 0.0))
            if np.isfinite(bin_id)
            else 0.0
        )
        new_entropy = float(self._entropy_d.get(int(new_bin_id), 0.0))

        assert self.mcusher is not None, "MCUsher is not initialized"
        log_factor = self.mcusher.compute_log_priori_factor(occupancy, step)
        exponent = entropy - new_entropy + log_factor
        self.trace.accepted = np.array(
            True if exponent >= 0 else exponent > log(self._rng.random())
        )
        return self.trace.accepted

    def _do_accept_step(self, occupancy: np.ndarray, step):
        occupancy = super()._do_accept_step(occupancy, step)
        self._current_features += self.trace.delta_trace.features
        self._current_enthalpy += self.trace.delta_trace.enthalpy
        self._last_accepted_occupancy = occupancy.copy()
        return occupancy

    def _do_post_step(self) -> None:
        bin_id = self._get_bin_id(self._current_enthalpy)

        if np.isfinite(bin_id):
            b = int(bin_id)

            prev_visits = int(self._occurrences_d.get(b, 0))
            new_visits = prev_visits + 1
            self._occurrences_d[b] = new_visits

            prev = self._mean_features_d.get(b)
            if prev is None:
                prev = np.zeros_like(self._current_features)
            self._mean_features_d[b] = (
                self._current_features + prev_visits * prev
            ) / float(new_visits)

            # Optional: capture up to K UNIQUE samples per bin
            if (
                self._samples_per_bin > 0
                and self._last_accepted_occupancy is not None
            ):
                lst = self._bin_samples_d.get(b)
                if lst is None:
                    lst = []
                    self._bin_samples_d[b] = lst
                if len(lst) < self._samples_per_bin:
                    h = self._hash_occupancy_int32(self._last_accepted_occupancy)
                    seen = self._bin_sample_hashes_d.get(b)
                    if seen is None:
                        seen = set()
                        self._bin_sample_hashes_d[b] = seen
                    if h not in seen:
                        lst.append(
                            [
                                int(x)
                                for x in np.asarray(
                                    self._last_accepted_occupancy, dtype=int
                                ).tolist()
                            ]
                        )
                        seen.add(h)
                        if len(lst) >= self._samples_per_bin:
                            self._bin_sample_hashes_d.pop(b, None)

            self._steps_counter += 1
            if self._steps_counter % self.update_period == 0:
                self._update_cation_stats_for_bin(b)
                if not self._production_mode:
                    self._entropy_d[b] = float(
                        self._entropy_d.get(b, 0.0) + self._m
                    )
                    self._histogram_d[b] = int(self._histogram_d.get(b, 0) + 1)

        self.trace.histogram = np.empty((0,), dtype=int)
        self.trace.occurrences = np.empty((0,), dtype=int)
        self.trace.entropy = np.empty((0,), dtype=float)
        self.trace.cumulative_mean_features = np.empty(
            (0, self._nfeat), dtype=float
        )
        self.trace.mod_factor = np.array([self._m])

        # Flatness check (disabled in production_mode)
        if (not self._production_mode) and (
            self._steps_counter % self.check_period == 0
        ):
            histogram = self.histogram
            if len(histogram) >= 2 and (
                histogram > self.flatness * histogram.mean()
            ).all():
                self._histogram_d.clear()
                self._m = self._mod_update(self._m)
                self._mod_updates_buf.append(
                    (int(self._steps_counter), float(self._m))
                )

    def pop_mod_updates(self) -> list[tuple[int, float]]:
        ev = self._mod_updates_buf
        self._mod_updates_buf = []
        return ev

    def pop_bin_samples(self) -> dict[int, list[list[int]]]:
        out = self._bin_samples_d
        self._bin_samples_d = {}
        self._bin_sample_hashes_d = {}
        return out

    def pop_bin_cation_counts(
        self,
    ) -> dict[int, dict[str, dict[str, dict[int, int]]]]:
        out = self._bin_cation_counts
        self._bin_cation_counts = {}
        return out

    def compute_initial_trace(self, occupancy: np.ndarray):
        trace = super().compute_initial_trace(occupancy)
        trace.histogram = np.empty((0,), dtype=int)
        trace.occurrences = np.empty((0,), dtype=int)
        trace.entropy = np.empty((0,), dtype=float)
        trace.cumulative_mean_features = np.empty((0, self._nfeat), dtype=float)
        trace.mod_factor = self._m
        return trace

    def set_aux_state(self, occupancy: np.ndarray, *args, **kwargs):
        features = np.array(self.ensemble.compute_feature_vector(occupancy))
        enthalpy = float(np.dot(features, self.natural_params))
        self._current_features = features
        self._current_enthalpy = enthalpy
        assert self.mcusher is not None, "MCUsher is not initialized"
        self.mcusher.set_aux_state(occupancy)

    # -------------------- checkpointing API --------------------

    def state(self) -> WLKernelState:
        bins = self.bin_indices
        occurrences = np.asarray(
            [self._occurrences_d.get(int(b), 0) for b in bins], dtype=int
        )
        mean_feats = (
            np.asarray(
                [self._mean_features_d[int(b)] for b in bins], dtype=float
            )
            if bins.size
            else np.empty((0, self._nfeat), dtype=float)
        )
        return WLKernelState(
            version=1,
            bin_indices=bins.tolist(),
            entropy=self.entropy.tolist(),
            histogram=self.histogram.tolist(),
            occurrences=occurrences.tolist(),
            mean_features=mean_feats.tolist(),
            mod_factor=float(self._m),
            steps_counter=int(self._steps_counter),
            current_enthalpy=float(self._current_enthalpy),
            current_features=np.asarray(
                self._current_features, dtype=float
            ).tolist(),
            rng_state=self._encode_rng_state(self._rng.bit_generator.state),
            bin_size=float(self._bin_size),
        )

    def load_state(self, s: WLKernelState | dict) -> None:
        if isinstance(s, WLKernelState):
            s = s.model_dump()
        self._entropy_d.clear()
        self._histogram_d.clear()
        self._occurrences_d.clear()
        self._mean_features_d.clear()
        self._bin_samples_d.clear()
        self._bin_sample_hashes_d.clear()
        self._bin_cation_counts.clear()

        bins = np.asarray(s["bin_indices"], dtype=int)
        ent = np.asarray(s["entropy"], dtype=float)
        hist = np.asarray(s["histogram"], dtype=int)
        occ = np.asarray(s["occurrences"], dtype=int)
        mfeat = np.asarray(s["mean_features"], dtype=float)

        for i, b in enumerate(bins):
            bi = int(b)
            self._entropy_d[bi] = float(ent[i])
            self._histogram_d[bi] = int(hist[i])
            self._occurrences_d[bi] = int(occ[i])
            self._mean_features_d[bi] = mfeat[i].astype(float, copy=False)

        self._m = float(s["mod_factor"])
        self._steps_counter = int(s["steps_counter"])
        self._current_enthalpy = float(s["current_enthalpy"])
        self._current_features = np.asarray(s["current_features"], dtype=float)
        self._mod_updates_buf = []
        self._rng.bit_generator.state = self._decode_rng_state(s["rng_state"])

        if "bin_size" in s and float(s["bin_size"]) != float(self._bin_size):
            raise ValueError(
                f"State bin_size {s['bin_size']} != kernel bin_size {self._bin_size}"
            )

    # ---------- RNG state (de)serialization helpers ----------

    @staticmethod
    def _encode_rng_state(st: Mapping[str, Any]) -> dict[str, Any]:
        INT64_MAX = (1 << 63) - 1

        def enc(x: Any) -> Any:
            if isinstance(x, dict):
                return {str(k): enc(v) for k, v in x.items()}
            if isinstance(x, (list, tuple, np.ndarray)):
                return [enc(v) for v in np.asarray(x).tolist()]
            if isinstance(x, (np.integer, int)):
                xi = int(x)
                if xi > INT64_MAX or xi < -INT64_MAX - 1:
                    return {"__u64__": hex(xi & ((1 << 64) - 1))}
                return xi
            return x

        res: Any = enc(dict(st))
        if not isinstance(res, dict):
            raise TypeError("Encoded RNG state must be a dict at the top level.")
        return dict(res)

    @staticmethod
    def _decode_rng_state(st: Mapping[str, Any]) -> dict[str, Any]:
        def dec(x: Any) -> Any:
            if isinstance(x, dict):
                if "__u64__" in x:
                    return int(x["__u64__"], 16)
                return {k: dec(v) for k, v in x.items()}
            if isinstance(x, list):
                return [dec(v) for v in x]
            return x

        res: Any = dec(dict(st))
        if not isinstance(res, dict):
            raise TypeError("Decoded RNG state must be a dict at the top level.")
        return dict(res)
