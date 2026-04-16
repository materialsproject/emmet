"""Integration test: replicate the phase-edge test_emmet.ipynb workflow
using the new emmet-integrated disorder builder."""

import math
import os
import pickle
import time

import numpy as np
from pymatgen.core import Lattice, Structure

from emmet.core.disorder import CationBinCount, DisorderDoc, DisorderedTaskDoc
from emmet.core.tasks import CoreTaskDoc
from emmet.builders.disorder.disorder import build_disorder_doc

DATA_DIR = "/scratch/cbu/test/spinel_Q0O/MgAl2O4_20meVpA"
CACHE_PATH = "/scratch/cbu/test/spinel_Q0O/MgAl2O4_20meVpA_docs.pkl"


def _make_ordered_task_doc() -> CoreTaskDoc:
    """Build a minimal CoreTaskDoc standing in for the ordered MgAl2O4 parent.

    Only the ``structure`` field is used by the builder (as meta_structure for
    populating search metadata).  Everything else gets default / None values.
    """
    # Fd-3m MgAl2O4 spinel primitive cell (approximate lattice param)
    lattice = Lattice.cubic(8.08)
    species = ["Mg"] * 8 + ["Al"] * 16 + ["O"] * 32
    # Wyckoff 8a (Mg), 16d (Al), 32e (O) positions in Fd-3m
    coords = [
        # 8a tetrahedral (Mg)
        [0.125, 0.125, 0.125], [0.125, 0.625, 0.625],
        [0.625, 0.125, 0.625], [0.625, 0.625, 0.125],
        [0.375, 0.375, 0.375], [0.375, 0.875, 0.875],
        [0.875, 0.375, 0.875], [0.875, 0.875, 0.375],
        # 16d octahedral (Al)
        [0.5, 0.5, 0.5], [0.5, 0.0, 0.0],
        [0.0, 0.5, 0.0], [0.0, 0.0, 0.5],
        [0.75, 0.75, 0.25], [0.75, 0.25, 0.75],
        [0.25, 0.75, 0.75], [0.25, 0.25, 0.25],
        [0.0, 0.0, 0.0], [0.0, 0.5, 0.5],
        [0.5, 0.0, 0.5], [0.5, 0.5, 0.0],
        [0.75, 0.25, 0.25], [0.25, 0.75, 0.25],
        [0.25, 0.25, 0.75], [0.75, 0.75, 0.75],
        # 32e (O) with u ≈ 0.3625
        [0.3625, 0.3625, 0.3625], [0.3625, 0.1375, 0.1375],
        [0.1375, 0.3625, 0.1375], [0.1375, 0.1375, 0.3625],
        [0.6375, 0.6375, 0.1375], [0.6375, 0.8625, 0.3625],
        [0.8625, 0.6375, 0.3625], [0.8625, 0.8625, 0.1375],
        [0.6375, 0.1375, 0.6375], [0.8625, 0.3625, 0.6375],
        [0.6375, 0.3625, 0.8625], [0.8625, 0.1375, 0.8625],
        [0.1375, 0.6375, 0.6375], [0.3625, 0.8625, 0.6375],
        [0.1375, 0.8625, 0.8625], [0.3625, 0.6375, 0.8625],
        [0.8625, 0.8625, 0.8625], [0.8625, 0.6375, 0.6375],
        [0.6375, 0.8625, 0.6375], [0.6375, 0.6375, 0.8625],
        [0.1375, 0.1375, 0.8625], [0.1375, 0.3625, 0.6375],
        [0.3625, 0.1375, 0.6375], [0.3625, 0.3625, 0.8625],
        [0.1375, 0.8625, 0.1375], [0.3625, 0.6375, 0.1375],
        [0.1375, 0.6375, 0.3625], [0.3625, 0.8625, 0.3625],
        [0.8625, 0.1375, 0.1375], [0.6375, 0.3625, 0.1375],
        [0.8625, 0.3625, 0.3625], [0.6375, 0.1375, 0.3625],
    ]
    struct = Structure(lattice, species, coords)
    return CoreTaskDoc.model_construct(structure=struct)


def load_docs():
    """Load docs from cache if available, otherwise parse from directories and save."""
    if os.path.exists(CACHE_PATH):
        print(f"Loading cached docs from {CACHE_PATH} ...")
        t = time.time()
        with open(CACHE_PATH, "rb") as f:
            docs = pickle.load(f)
        print(f"Loaded {len(docs)} docs from cache in {time.time() - t:.1f}s")
        return docs

    print(f"No cache found, loading from {DATA_DIR} ...")
    dir_list = sorted(os.listdir(DATA_DIR))
    docs = []
    for i, subdir in enumerate(dir_list):
        full_path = os.path.join(DATA_DIR, subdir)
        if not os.path.isdir(full_path):
            raise ValueError(f"{full_path} is not a directory")
        doc, _ = DisorderedTaskDoc.from_directory(full_path)
        if (i + 1) % 50 == 0 or i == 0:
            print(f"{i + 1}/{len(dir_list)} loaded")
        docs.append(doc)

    print(f"Saving {len(docs)} docs to {CACHE_PATH} ...")
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(docs, f, protocol=pickle.HIGHEST_PROTOCOL)
    print("Cache saved.")
    return docs


def main():
    t0 = time.time()

    docs = load_docs()
    print(f"\n{len(docs)} DisorderedTaskDocs ready in {time.time() - t0:.1f}s")

    # --- Run the builder ---
    ordered_task_doc = _make_ordered_task_doc()
    t1 = time.time()
    result = build_disorder_doc(docs, ordered_task_doc)
    t2 = time.time()

    # --- Print results ---
    print(f"\nbuild_disorder_doc completed in {t2 - t1:.1f}s")
    print(f"  ordered_task_id:  {result.ordered_task_id}")
    print(f"  prototype:        {result.prototype}")
    print(f"  supercell_diag:   {result.supercell_diag}")
    print(f"  sublattices:      {result.sublattices}")
    print(f"  # training docs:  {len(result.disordered_task_ids)}")
    print(f"  training_stats:   {result.training_stats}")
    print(f"  design_metrics:   {result.design_metrics}")
    print(f"  WL final mod_factor: {result.wl_dos.mod_factor}")
    print(f"  WL # bins:        {len(result.wl_dos.bin_indices)}")
    print(f"  WL occupancy len: {len(result.wl_occupancy)}")
    print(f"  # cation_counts:  {len(result.cation_counts)}")
    print(f"  chemsys:          {result.chemsys}")
    print(f"  elements:         {result.elements}")
    print(f"  formula_pretty:   {result.formula_pretty}")

    # --- Post-processing: x(E), x(T), purity(T) ---
    print("\n--- Post-processing ---")
    verify_postprocessing(result)

    print(f"\nTotal time: {t2 - t0:.1f}s")
    print("PASS")


# ---------------------------------------------------------------------------
# Post-processing utilities
# ---------------------------------------------------------------------------

kB_eV_per_K = 8.617333262145e-5


def _aggregate_cation_counts(
    rows: list[CationBinCount],
) -> dict[int, dict[str, dict[str, dict[int, int]]]]:
    """Aggregate typed rows into: agg[bin][sublattice][element][n_sites] = visits."""
    agg: dict[int, dict[str, dict[str, dict[int, int]]]] = {}
    for r in rows:
        d = agg.setdefault(r.bin, {}).setdefault(r.sublattice, {}).setdefault(r.element, {})
        d[r.n_sites] = d.get(r.n_sites, 0) + r.count
    return agg


def _compute_xE(
    cation_agg: dict[int, dict[str, dict[str, dict[int, int]]]],
) -> dict[str, dict[str, dict[int, float]]]:
    """x(E): fraction of sublattice occupied by each element per energy bin."""
    xE: dict[str, dict[str, dict[int, float]]] = {}
    for b, sl_dict in cation_agg.items():
        for sl, elem_dict in sl_dict.items():
            den = sum(
                float(n_sites) * float(cnt)
                for hist in elem_dict.values()
                for n_sites, cnt in hist.items()
            )
            if den <= 0.0:
                continue
            for elem, hist in elem_dict.items():
                num = sum(float(n_sites) * float(cnt) for n_sites, cnt in hist.items())
                xE.setdefault(sl, {}).setdefault(elem, {})[b] = num / den
    return xE


def _compute_purityE(
    cation_agg: dict[int, dict[str, dict[str, dict[int, int]]]],
) -> tuple[dict[str, dict[str, dict[int, float]]], dict[str, int]]:
    """purityE: average purity per bin for each (sublattice, element)."""
    sublat_sizes: dict[str, int] = {}
    for sl_dict in cation_agg.values():
        for sl, elem_dict in sl_dict.items():
            for hist in elem_dict.values():
                for n_sites in hist:
                    sublat_sizes[sl] = max(sublat_sizes.get(sl, 0), n_sites)

    purityE: dict[str, dict[str, dict[int, float]]] = {}
    for b, sl_dict in cation_agg.items():
        for sl, elem_dict in sl_dict.items():
            N = sublat_sizes.get(sl)
            if not N:
                continue
            Nf = float(N)
            for elem, hist in elem_dict.items():
                total_visits = sum(hist.values())
                if total_visits <= 0:
                    continue
                purity_sum = sum(
                    (max(n, N - n) / Nf) * float(cnt)
                    for n, cnt in hist.items()
                )
                purityE.setdefault(sl, {}).setdefault(elem, {})[b] = purity_sum / float(total_visits)
    return purityE, sublat_sizes


def _softmax(log_weights: np.ndarray) -> np.ndarray:
    if log_weights.size == 0:
        return np.array([], dtype=float)
    m = float(np.max(log_weights))
    w = np.exp(log_weights - m)
    s = float(np.sum(w))
    if s == 0.0 or not math.isfinite(s):
        return np.ones_like(log_weights) / float(log_weights.size)
    return w / s


def _canonical_average(
    propE: dict[str, dict[str, dict[int, float]]],
    S_map: dict[int, float],
    E_map: dict[int, float],
    T_grid: np.ndarray,
) -> dict[str, dict[str, dict[float, float]]]:
    """Canonical average: prop(T) = sum_b w_b(T) * prop(E_b)."""
    propT: dict[str, dict[str, dict[float, float]]] = {}
    for sl, elem_bins in propE.items():
        for elem, prop_bins in elem_bins.items():
            bins = sorted(b for b in prop_bins if b in S_map and b in E_map)
            if not bins:
                continue
            S_vec = np.array([S_map[b] for b in bins])
            E_vec = np.array([E_map[b] for b in bins])
            prop_vec = np.array([prop_bins[b] for b in bins])

            for T in T_grid:
                inv_kT = 1.0 / (kB_eV_per_K * T)
                logw = S_vec - E_vec * inv_kT
                weights = _softmax(logw)
                propT.setdefault(sl, {}).setdefault(elem, {})[float(T)] = float(np.dot(weights, prop_vec))
    return propT


def verify_postprocessing(result: DisorderDoc) -> None:
    """Compute x(E), x(T), purity(T) from a DisorderDoc and print diagnostics."""
    wl = result.wl_dos
    bin_indices = np.array(wl.bin_indices, dtype=int)
    entropy = np.array(wl.entropy, dtype=float)
    bin_size = wl.bin_size

    S_map = {int(b): float(entropy[i]) for i, b in enumerate(bin_indices)}
    E_map = {int(b): float(b) * bin_size for b in bin_indices}

    cation_agg = _aggregate_cation_counts(result.cation_counts)
    assert len(cation_agg) > 0, "No cation counts aggregated"

    xE = _compute_xE(cation_agg)
    assert len(xE) > 0, "x(E) is empty"

    purityE, sublat_sizes = _compute_purityE(cation_agg)
    assert len(purityE) > 0, "purity(E) is empty"

    T_grid = np.linspace(500.0, 2500.0, 200)
    xT = _canonical_average(xE, S_map, E_map, T_grid)
    purityT = _canonical_average(purityE, S_map, E_map, T_grid)

    # Print summary
    print(f"  cation_agg bins: {len(cation_agg)}")
    print(f"  sublat_sizes: {sublat_sizes}")
    for sl in sorted(xE):
        for elem in sorted(xE[sl]):
            n_bins = len(xE[sl][elem])
            xE_vals = list(xE[sl][elem].values())
            print(f"  x(E) [{sl}/{elem}]: {n_bins} bins, range [{min(xE_vals):.4f}, {max(xE_vals):.4f}]")
    for sl in sorted(xT):
        for elem in sorted(xT[sl]):
            T_vals = sorted(xT[sl][elem].keys())
            x_lo = xT[sl][elem][T_vals[0]]
            x_hi = xT[sl][elem][T_vals[-1]]
            print(f"  x(T) [{sl}/{elem}]: T={T_vals[0]:.0f}K -> x={x_lo:.4f}, T={T_vals[-1]:.0f}K -> x={x_hi:.4f}")
    for sl in sorted(purityT):
        for elem in sorted(purityT[sl]):
            T_vals = sorted(purityT[sl][elem].keys())
            p_lo = purityT[sl][elem][T_vals[0]]
            p_hi = purityT[sl][elem][T_vals[-1]]
            print(f"  purity(T) [{sl}/{elem}]: T={T_vals[0]:.0f}K -> p={p_lo:.4f}, T={T_vals[-1]:.0f}K -> p={p_hi:.4f}")

    # Basic sanity checks
    for sl in xT:
        for elem in xT[sl]:
            for T, x in xT[sl][elem].items():
                assert 0.0 <= x <= 1.0, f"x(T) out of range: {x} at T={T}"
    for sl in purityT:
        for elem in purityT[sl]:
            for T, p in purityT[sl][elem].items():
                assert 0.5 - 1e-9 <= p <= 1.0 + 1e-9, f"purity(T) out of range: {p} at T={T}"
    print("  Post-processing checks PASSED")


if __name__ == "__main__":
    main()
