"""Hashing and key-computation utilities for CE and WL identity.

Vendored from phaseedge.utils.keys with imports adjusted.
Only the functions needed by the builder are included.
"""

import hashlib
import json
from typing import Any, Mapping

import numpy as np

from emmet.builders.disorder.mixture import canonical_comp_map


# -------------------- canonicalization helpers --------------------

def _json_canon(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_canon(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_json_canon(x) for x in obj]
    if isinstance(obj, np.ndarray):
        return _json_canon(obj.tolist())
    return obj


def _round_float(x: float, ndigits: int = 12) -> float:
    return float(f"{x:.{ndigits}g}")


def _canon_num(v: Any, ndigits: int = 12) -> Any:
    if isinstance(v, float):
        return _round_float(v, ndigits)
    if isinstance(v, (list, tuple)):
        return [_canon_num(x, ndigits) for x in v]
    if isinstance(v, dict):
        return {str(k): _canon_num(v[k], ndigits) for k in sorted(v)}
    return v


# -------------------- Wang-Landau chain key --------------------

def compute_wl_key(
    *,
    ce_key: str,
    bin_width: float,
    step_type: str,
    initial_comp_map: Mapping[str, Mapping[str, int]],
    reject_cross_sublattice_swaps: bool,
    check_period: int,
    update_period: int,
    seed: int,
    algo_version: str,
) -> str:
    payload = {
        "kind": "wl_key",
        "algo_version": algo_version,
        "ce_key": str(ce_key),
        "ensemble": {
            "type": "canonical",
            "init_comp_map": canonical_comp_map(initial_comp_map),
        },
        "grid": {
            "bin_width": _round_float(float(bin_width)),
        },
        "mc": {
            "reject_cross_sublattice_swaps": bool(reject_cross_sublattice_swaps),
            "step_type": str(step_type),
            "check_period": int(check_period),
            "update_period": int(update_period),
            "seed": int(seed),
        },
    }
    blob = json.dumps(
        _json_canon(_canon_num(payload)), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compute_wl_block_key(
    *,
    wl_key: str,
    parent_wl_block_key: str,
    state: Mapping[str, Any],
    occupancy: np.ndarray,
) -> str:
    """Compute a canonical WL chunk key for immutable block identity."""
    payload = {
        "wl_key": wl_key,
        "parent_wl_block_key": parent_wl_block_key,
        "state": _json_canon(state),
        "occupancy": occupancy.astype(int).tolist(),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
