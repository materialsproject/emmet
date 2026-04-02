"""Design-matrix diagnostics for CE training.

Vendored from phaseedge.science.design_metrics with imports adjusted.
"""

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from emmet.core.disorder import CEDesignMetrics


@dataclass(slots=True)
class MetricOptions:
    """Options controlling how we compute design metrics."""

    standardize: bool = True
    eps: float = 1e-12


def _standardize_columns(
    X: NDArray[np.float64], eps: float
) -> tuple[NDArray[np.float64], int]:
    """Column z-score standardization."""
    Xc = X - X.mean(axis=0, keepdims=True)
    std = Xc.std(axis=0, ddof=0, keepdims=True)

    zero_var_mask = std <= eps
    zero_var_count = int(zero_var_mask.sum())

    std_safe = std.copy()
    std_safe[std_safe <= eps] = 1.0

    Xz = Xc / std_safe
    return cast(NDArray[np.float64], Xz), zero_var_count


def compute_design_metrics(
    *,
    X: NDArray[np.float64],
    w: NDArray[np.float64] | None = None,
    options: MetricOptions | None = None,
) -> CEDesignMetrics:
    """Compute design-matrix diagnostics for CE training."""
    if X.ndim != 2:
        raise ValueError(f"X must be 2D, got shape {X.shape!r}")
    n, p = map(int, X.shape)
    if n == 0 or p == 0:
        raise ValueError("X must have non-zero shape.")

    opts = options or MetricOptions()
    eps = float(opts.eps)

    # Apply weights as in training: Xw = diag(sqrt(w)) @ X
    if w is not None:
        if w.ndim != 1 or int(w.size) != n:
            raise ValueError(f"w must be length-{n} vector; got shape {w.shape!r}")
        sqrt_w = np.sqrt(w, dtype=np.float64).reshape(-1, 1)
        Xw = X * sqrt_w
    else:
        Xw = X
    weighting_applied = w is not None

    if opts.standardize:
        Xm, zero_var_count = _standardize_columns(Xw, eps)
        std_mode = "column_zscore"
    else:
        Xm = Xw
        zero_var_count = 0
        std_mode = "none"

    # SVD-based metrics (economy SVD)
    U, s, _ = np.linalg.svd(Xm, full_matrices=False)
    keep = s > eps
    rank = int(keep.sum())

    sigma_max = float(s[0]) if s.size > 0 else 0.0
    sigma_min = float(s[rank - 1]) if rank > 0 else 0.0

    if rank == 0 or sigma_min <= eps:
        condition_number = float("inf")
    else:
        condition_number = float(sigma_max / sigma_min)

    positive = s[keep]
    if positive.size == 0:
        logdet_xtx = float("-inf")
    else:
        logdet_xtx = float(2.0 * np.log(positive).sum())

    # Leverage diagnostics via U_r
    if rank > 0:
        Ur = U[:, :rank]
        lev = np.einsum("ij,ij->i", Ur, Ur, optimize=True)
        leverage_mean = float(lev.mean())
        leverage_max = float(lev.max(initial=0.0))
        leverage_p95 = float(np.percentile(lev, 95.0))
    else:
        leverage_mean = leverage_max = leverage_p95 = float("nan")

    return CEDesignMetrics(
        n_samples=n,
        n_features=p,
        rank=rank,
        sigma_max=sigma_max,
        sigma_min=sigma_min,
        condition_number=condition_number,
        logdet_xtx=logdet_xtx,
        leverage_mean=leverage_mean,
        leverage_max=leverage_max,
        leverage_p95=leverage_p95,
        weighting_applied=weighting_applied,
        standardization=cast(Any, std_mode),
        zero_variance_feature_count=zero_var_count,
    )
