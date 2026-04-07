"""Cluster Expansion training driver.

Vendored from phaseedge.sampling.train_ce_driver with imports adjusted.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, cast

import numpy as np
from ase.atoms import Atoms
from numpy.typing import NDArray
from pymatgen.core import DummySpecies, Element, Structure
from pymatgen.entries.computed_entries import ComputedStructureEntry
from pymatgen.io.ase import AseAtomsAdaptor
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold
from smol.cofe import ClusterExpansion, ClusterSubspace, StructureWrangler

from emmet.builders.disorder.design_metrics import (
    MetricOptions,
    compute_design_metrics,
)
from emmet.builders.disorder.prototype_spec import PrototypeSpec
from emmet.core.disorder import (
    CECompositionStats,
    CEDesignMetrics,
    CEFitMetrics,
    CETrainingStats,
)


@dataclass(slots=True)
class TrainOutput:
    """Output of run_train_ce: typed CE training results."""

    payload: dict[str, Any]
    stats: CETrainingStats
    design_metrics: CEDesignMetrics


@dataclass(slots=True)
class BasisSpec:
    """Minimal basis spec for CE."""

    cutoffs: Mapping[Any, Any]
    basis: str = "sinusoid"

    def __post_init__(self) -> None:
        self.cutoffs = {int(k): float(v) for k, v in dict(self.cutoffs).items()}


@dataclass(slots=True)
class Regularization:
    """Regularization options for the linear solve."""

    type: str = "ols"
    alpha: float = 1e-6
    l1_ratio: float = 0.5


def build_disordered_primitive(
    primitive_cell: Atoms,
    sublattices: dict[str, tuple[str, ...]],
) -> Structure:
    """Create the CE parent primitive with disordered site space."""
    if not sublattices:
        raise ValueError("sublattices must be non-empty.")

    prim_cfg = AseAtomsAdaptor.get_structure(primitive_cell)
    replace_elements = tuple(sublattices.keys())
    disordered_map: dict[Any, dict[Any, float]] = {}
    for replace_element, allowed_species in sublattices.items():
        species_and_labels = tuple(allowed_species) + replace_elements
        frac = 1.0 / len(species_and_labels)
        replace_key = (
            DummySpecies(replace_element)
            if replace_element == "X"
            else Element(replace_element)
        )
        disordered_map[replace_key] = {}
        for el in species_and_labels:
            key = DummySpecies(el) if el == "X" else Element(el)
            disordered_map[replace_key][key] = frac

    prim_cfg.replace_species(disordered_map)
    return prim_cfg


def featurize_structures(
    subspace: ClusterSubspace,
    structures: Sequence[Structure],
    supercell_diag: tuple[int, int, int],
) -> tuple[StructureWrangler, NDArray[np.float64]]:
    """Build a StructureWrangler and feature matrix X for the given structures."""
    nx, ny, nz = map(int, supercell_diag)
    sc_mat = np.diag((nx, ny, nz))

    wrangler = StructureWrangler(subspace)
    site_map = None

    for s in structures:
        if not isinstance(s, Structure):
            raise TypeError(f"Expected pymatgen Structure, got {type(s)!r}")
        entry = ComputedStructureEntry(structure=s, energy=0.0)
        wrangler.add_entry(
            entry,
            supercell_matrix=sc_mat,
            site_mapping=site_map,
            verbose=False,
        )
        if site_map is None and wrangler.entries:
            site_map = wrangler.entries[-1].data.get("site_mapping")

    X = wrangler.feature_matrix
    if X.size == 0 or X.shape[1] == 0:
        raise ValueError(
            "Feature matrix is empty (no clusters generated). "
            "Increase cutoffs or adjust the basis specification."
        )
    return wrangler, X


def fit_linear_model(
    X: NDArray[np.float64], y: NDArray[np.float64], reg: Regularization
) -> NDArray[np.float64]:
    """Solve for ECIs under the requested regularization."""
    t = reg.type.lower()
    if t == "ols":
        model = LinearRegression(fit_intercept=False)
    elif t == "ridge":
        model = Ridge(alpha=reg.alpha, fit_intercept=False)
    elif t == "lasso":
        model = Lasso(alpha=reg.alpha, fit_intercept=False, max_iter=10000)
    elif t == "elasticnet":
        model = ElasticNet(
            alpha=reg.alpha,
            l1_ratio=reg.l1_ratio,
            fit_intercept=False,
            max_iter=10000,
        )
    else:
        raise ValueError(f"Unknown regularization type: {reg.type}")

    model.fit(X, y)
    return cast(NDArray[np.float64], model.coef_.astype(np.float64, copy=False))


def predict_from_features(
    X: NDArray[np.float64], coefs: NDArray[np.float64]
) -> NDArray[np.float64]:
    return cast(NDArray[np.float64], (X @ coefs).astype(np.float64, copy=False))


def compute_stats(y_true: Sequence[float], y_pred: Sequence[float]) -> CEFitMetrics:
    if len(y_true) != len(y_pred) or len(y_true) == 0:
        raise ValueError("Stats require non-empty equal-length arrays.")
    n = len(y_true)
    abs_err = [abs(a - b) for a, b in zip(y_true, y_pred)]
    mae = float(sum(abs_err) / n)
    rmse = float(mean_squared_error(y_true, y_pred) ** 0.5)
    mex = float(max(abs_err))
    return CEFitMetrics(n=n, mae_per_site=mae, rmse_per_site=rmse, max_abs_per_site=mex)


def _n_replace_sites_from_prototype(
    prototype_spec: PrototypeSpec,
    supercell_diag: tuple[int, int, int],
) -> int:
    """Count the number of active sites in the supercell."""
    n_per_prim = sum(prototype_spec.active_sublattice_counts.values())
    nx, ny, nz = supercell_diag
    return int(n_per_prim) * nx * ny * nz


def _composition_signature(s: Structure) -> str:
    counts: dict[str, int] = {}
    for site in s.sites:
        sym = getattr(getattr(site, "specie", None), "symbol", None)
        if not isinstance(sym, str):
            sym = str(getattr(site, "specie", ""))
        if sym not in counts:
            counts[sym] = 0
        counts[sym] += 1
    parts = [f"{el}:{int(counts[el])}" for el in sorted(counts)]
    return ",".join(parts)


def _stats_for_group(
    idxs: Sequence[int],
    y_true_per_prim: Sequence[float],
    y_pred_per_prim: Sequence[float],
    sites_per_prim: int,
) -> CEFitMetrics:
    if not idxs:
        return CEFitMetrics(
            n=0, mae_per_site=0.0, rmse_per_site=0.0, max_abs_per_site=0.0,
        )
    scale = 1.0 / float(sites_per_prim)
    yt = [y_true_per_prim[i] * scale for i in idxs]
    yp = [y_pred_per_prim[i] * scale for i in idxs]
    return compute_stats(yt, yp)


def _build_sample_weights(
    comp_to_indices: Mapping[str, Sequence[int]],
    n_total: int,
    weighting: Mapping[str, Any] | None,
) -> np.ndarray:
    """Build per-sample weights."""
    w = np.ones(n_total, dtype=np.float64)
    if not weighting:
        return w

    scheme = str(weighting.get("scheme", "")).lower()
    alpha = float(weighting.get("alpha", 1.0))

    if scheme in ("balance_by_comp",):
        for idxs in comp_to_indices.values():
            n_g = max(1, len(idxs))
            base = (1.0 / float(n_g)) ** alpha
            for i in idxs:
                w[int(i)] = base
        s = float(w.sum())
        if s > 0:
            w *= n_total / s
        return w

    raise ValueError(f"Unknown weighting scheme: {scheme!r}")


def run_train_ce(
    structures_pm: Sequence[Structure],
    y_cell: Sequence[float],
    prototype_spec: PrototypeSpec,
    supercell_diag: tuple[int, int, int],
    sublattices: dict[str, tuple[str, ...]],
    basis_spec: Mapping[str, Any],
    regularization: Mapping[str, Any],
    weighting: Mapping[str, Any] | None = None,
    cv_seed: int | None = None,
) -> TrainOutput:
    """Train a Cluster Expansion with targets normalized per primitive cell.

    All stored stats are reported in per-site units.
    """
    n_prims = int(np.prod(supercell_diag))
    n_sites_const = _n_replace_sites_from_prototype(
        prototype_spec=prototype_spec,
        supercell_diag=supercell_diag,
    )
    sites_per_prim = n_sites_const // n_prims

    # Build disordered primitive and subspace
    primitive_cfg = build_disordered_primitive(
        primitive_cell=prototype_spec.primitive_cell, sublattices=sublattices
    )

    basis = BasisSpec(**cast(Mapping[str, Any], basis_spec))
    subspace = ClusterSubspace.from_cutoffs(
        structure=primitive_cfg,
        cutoffs=dict(basis.cutoffs),
        basis=basis.basis,
    )

    # Featurization
    _, X = featurize_structures(
        subspace=subspace, structures=structures_pm, supercell_diag=supercell_diag
    )
    if X.size == 0 or X.shape[1] == 0:
        raise ValueError(
            "Feature matrix is empty (no clusters generated). "
            "Try increasing cutoffs or adjusting the basis specification."
        )
    if X.shape[0] != len(y_cell):
        raise RuntimeError(
            f"Feature/target mismatch: X has {X.shape[0]} rows, y has {len(y_cell)}."
        )

    # Group by composition
    comp_to_indices: dict[str, list[int]] = {}
    for i, s in enumerate(structures_pm):
        sig = _composition_signature(s)
        comp_to_indices.setdefault(sig, []).append(i)

    # Weights
    n = X.shape[0]
    y = np.asarray(y_cell, dtype=np.float64)
    w = _build_sample_weights(comp_to_indices, n_total=n, weighting=weighting)
    sqrt_w = np.sqrt(w, dtype=np.float64)

    # Design diagnostics
    design = compute_design_metrics(
        X=X, w=w, options=MetricOptions(standardize=True, eps=1e-12)
    )

    # Fit linear model on full set (weighted)
    Xw = X * sqrt_w[:, None]
    yw = y * sqrt_w
    reg = Regularization(**cast(Mapping[str, Any], regularization))
    coefs = fit_linear_model(Xw, yw, reg)
    y_pred_in = predict_from_features(X, coefs).tolist()

    # Per-site metrics
    scale = 1.0 / float(sites_per_prim)
    y_true_site_vec = [v * scale for v in y_cell]
    y_pred_site_vec = [v * scale for v in y_pred_in]
    stats_in = compute_stats(y_true_site_vec, y_pred_site_vec)

    # Per-composition in-sample
    by_comp_in: dict[str, CEFitMetrics] = {}
    for sig, idxs in comp_to_indices.items():
        by_comp_in[sig] = _stats_for_group(
            idxs, y_cell, y_pred_in, sites_per_prim=sites_per_prim
        )

    # 5-fold CV
    k_splits = min(5, n)
    if k_splits >= 2:
        kf = KFold(
            n_splits=k_splits,
            shuffle=True,
            random_state=int(cv_seed) if cv_seed is not None else None,
        )
        y_pred_oof = np.empty(n, dtype=np.float64)
        y_pred_oof[:] = np.nan
        for train_idx, test_idx in kf.split(X):
            sw_tr = sqrt_w[train_idx]
            X_tr = X[train_idx] * sw_tr[:, None]
            y_tr = y[train_idx] * sw_tr
            coefs_fold = fit_linear_model(X_tr, y_tr, reg)
            y_pred_oof[test_idx] = predict_from_features(X[test_idx], coefs_fold)
        if np.isnan(y_pred_oof).any():
            y_pred_oof = np.where(
                np.isnan(y_pred_oof),
                np.asarray(y_pred_in, dtype=np.float64),
                y_pred_oof,
            )

        stats_cv = compute_stats(
            [v * scale for v in y_cell],
            [float(v) * scale for v in y_pred_oof],
        )

        by_comp_cv: dict[str, CEFitMetrics] = {}
        y_oof_list = y_pred_oof.tolist()
        for sig, idxs in comp_to_indices.items():
            by_comp_cv[sig] = _stats_for_group(
                idxs, y_cell, y_oof_list, sites_per_prim=sites_per_prim
            )
    else:
        stats_cv = stats_in
        by_comp_cv = by_comp_in

    # Assemble CE and payload
    ce = ClusterExpansion(subspace, coefs)
    return TrainOutput(
        payload=dict(ce.as_dict()),
        stats=CETrainingStats(
            in_sample=stats_in,
            five_fold_cv=stats_cv,
            by_composition={
                sig: CECompositionStats(
                    in_sample=by_comp_in[sig],
                    five_fold_cv=by_comp_cv[sig],
                )
                for sig in sorted(comp_to_indices)
            },
        ),
        design_metrics=design,
    )
