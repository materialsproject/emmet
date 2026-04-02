"""Wang-Landau block sampling driver.

Vendored from phaseedge.sampling.wl_block_driver with imports adjusted.
"""

from typing import Any, Mapping, TypedDict

import numpy as np
from pymatgen.core import Structure
from smol.moca import Sampler
from smol.moca.ensemble import Ensemble

from emmet.builders.disorder.infinite_wang_landau import InfiniteWangLandau, WLKernelState  # noqa: F401 — ensures registered
from emmet.builders.disorder.prototype_spec import PrototypeSpec
from emmet.builders.disorder.random_configs import make_one_snapshot
from emmet.builders.disorder.wl_sampler_spec import WLSamplerSpec


class WLBlockDoc(TypedDict, total=False):
    step_end: int
    cation_counts: list[dict[str, Any]]
    state: WLKernelState
    occupancy: list[int]


# ---- shared helpers -------------------------------------------------------


def _occ_from_initial_comp_map(
    *,
    prototype_spec: PrototypeSpec,
    supercell_diag: tuple[int, int, int],
    ensemble: Ensemble,
    initial_comp_map: Mapping[str, Mapping[str, int]],
    rng: np.random.Generator,
) -> np.ndarray:
    """Create ONE valid snapshot and encode occupancy for the ensemble."""
    struct = make_one_snapshot(
        primitive_cell=prototype_spec.primitive_cell,
        supercell_diag=supercell_diag,
        composition_map=initial_comp_map,
        rng=rng,
    )
    occ = ensemble.processor.cluster_subspace.occupancy_from_structure(
        struct, encode=True
    )
    occ = np.asarray(occ, dtype=np.int32)
    n_sites = getattr(ensemble.processor, "num_sites", occ.shape[0])
    if occ.shape[0] != n_sites:
        raise RuntimeError(
            f"Occupancy length {occ.shape[0]} != processor sites {n_sites}"
        )
    return occ


def _build_sublattices(
    *,
    prototype_spec: PrototypeSpec,
    supercell_diag: tuple[int, int, int],
) -> tuple[dict[str, dict[str, int]], Structure]:
    rng = np.random.default_rng(12345)
    sx, sy, sz = supercell_diag
    multiplier = sx * sy * sz
    sl_comp_map = {
        k: {k: v * multiplier}
        for k, v in prototype_spec.active_sublattice_counts.items()
    }
    struct = make_one_snapshot(
        primitive_cell=prototype_spec.primitive_cell,
        supercell_diag=(sx, sy, sz),
        composition_map=sl_comp_map,
        rng=rng,
    )
    return sl_comp_map, struct


def _build_sublattice_indices(
    *,
    ensemble: Ensemble,
    sl_struct: Structure,
    sl_comp_map: dict[str, dict[str, int]],
) -> dict[str, tuple[np.ndarray, dict[int, str]]]:
    """Build label -> site-index map from the CE prototype+supercell used by WL."""
    occ = ensemble.processor.cluster_subspace.occupancy_from_structure(
        sl_struct, encode=False
    )
    sl_map: dict[str, tuple[np.ndarray, dict[int, str]]] = {}
    for sublattice in ensemble.active_sublattices:
        code_to_elem = {
            int(code): str(elem)
            for code, elem in zip(sublattice.encoding, sublattice.species)
        }
        for elem in [str(s) for s in sublattice.species]:
            if elem not in sl_comp_map:
                continue
            idx = np.where([str(o.symbol) == elem for o in occ])[0]
            idx = idx[np.isin(idx, sublattice.sites)]
            if idx.size == 0:
                continue
            if elem in sl_map:
                raise ValueError(
                    f"Placeholder '{elem}' appears in multiple sublattices."
                )
            sl_map[elem] = (idx, code_to_elem)

    for placeholder in sl_comp_map.keys():
        if placeholder not in sl_map:
            raise ValueError(
                f"Could not find sites for sublattice placeholder '{placeholder}'."
            )

    return sl_map


# ---- Chunk runner ---------------------------------------------------------


def run_wl_block(
    spec: WLSamplerSpec,
    ensemble: Ensemble,
    tip: WLBlockDoc | None,
    prototype_spec: PrototypeSpec,
    supercell_diag: tuple[int, int, int],
) -> WLBlockDoc:
    rng = np.random.default_rng(int(spec.seed))

    sl_comp_map, sl_struct = _build_sublattices(
        prototype_spec=prototype_spec, supercell_diag=supercell_diag
    )
    sublattice_indices = _build_sublattice_indices(
        ensemble=ensemble, sl_struct=sl_struct, sl_comp_map=sl_comp_map
    )

    sampler = Sampler.from_ensemble(
        ensemble,
        kernel_type="InfiniteWangLandau",
        bin_size=spec.bin_width,
        step_type=spec.step_type,
        flatness=0.8,
        seeds=[int(spec.seed)],
        check_period=spec.check_period,
        update_period=spec.update_period,
        samples_per_bin=int(spec.samples_per_bin),
        collect_cation_stats=spec.collect_cation_stats,
        production_mode=spec.production_mode,
        sublattice_indices=sublattice_indices,
        reject_cross_sublattice_swaps=spec.reject_cross_sublattice_swaps,
    )

    if tip is None:
        step_start = 0
        occ = _occ_from_initial_comp_map(
            prototype_spec=prototype_spec,
            supercell_diag=supercell_diag,
            ensemble=ensemble,
            initial_comp_map=spec.initial_comp_map,
            rng=rng,
        )
    else:
        step_start = int(tip["step_end"])
        occ = np.asarray(tip["occupancy"], dtype=np.int32)
        sampler.mckernels[0].load_state(tip["state"])

    thin_by = max(1, spec.steps)
    sampler.run(spec.steps, occ, thin_by=thin_by, progress=False)

    k = sampler.mckernels[0]
    end_state = k.state()
    occ_last = (
        sampler.samples.get_occupancies(flat=False)[-1][0].astype(np.int32)
    )

    # Clear internal buffers to prevent unbounded memory growth across blocks.
    k.pop_mod_updates()
    k.pop_bin_samples()
    bin_cation_counts = k.pop_bin_cation_counts()

    cation_counts_flat: list[dict[str, Any]] = [
        {
            "bin": int(b),
            "sublattice": sl,
            "element": elem,
            "n_sites": int(n_sites),
            "count": int(count),
        }
        for b, sl_map in bin_cation_counts.items()
        for sl, elem_map in sl_map.items()
        for elem, hist in elem_map.items()
        for n_sites, count in hist.items()
    ]

    return {
        "step_end": step_start + spec.steps,
        "cation_counts": cation_counts_flat,
        "state": end_state,
        "occupancy": occ_last.tolist(),
    }
