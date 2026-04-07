"""Builder function for creating DisorderDoc from DisorderedTaskDoc instances.

Follows the functional builder pattern used in emmet-builders (see vasp/materials.py).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from smol.cofe import ClusterExpansion
from smol.moca.ensemble import Ensemble

from emmet.core.disorder import CationBinCount, DisorderDoc, DisorderedTaskDoc, WLDensityOfStates, WLSpecParams
from emmet.core.tasks import CoreTaskDoc

from .mixture import sublattices_from_composition_maps
from .prototype_spec import PrototypeSpec
from .train_ce import run_train_ce
from .wl_sampling import run_wl_block

# Default CE training hyper-parameters
_DEFAULT_BASIS_SPEC: dict[str, Any] = {"basis": "sinusoid", "cutoffs": {2: 10, 3: 8, 4: 5}}
_DEFAULT_REGULARIZATION: dict[str, Any] = {"type": "ridge", "alpha": 1e-3, "l1_ratio": 0.5}
_DEFAULT_WEIGHTING: dict[str, Any] = {"scheme": "balance_by_comp", "alpha": 1.0}
_DEFAULT_CV_SEED: int = 42

# Default WL sampling hyper-parameters
_DEFAULT_WL_STEPS: int = 1_000_000
_DEFAULT_WL_CHECK_PERIOD: int = 5000
_DEFAULT_WL_UPDATE_PERIOD: int = 1
_DEFAULT_WL_SEED: int = 0
_DEFAULT_WL_CONVERGENCE_THRESHOLD: float = 1e-7
_DEFAULT_BIN_WIDTH: float = 0.1
_DEFAULT_MIN_BINS: int = 50
_DEFAULT_MAX_BINS: int = 200
_DEFAULT_MAX_BIN_REFINEMENTS: int = 20
_DEFAULT_MAX_WL_BLOCKS: int = 200


def build_disorder_doc(
    disordered_documents: list[DisorderedTaskDoc],
    ordered_task_doc: CoreTaskDoc,
    basis_spec: dict[str, Any] | None = None,
    regularization: dict[str, Any] | None = None,
    weighting: dict[str, Any] | None = None,
    cv_seed: int | None = _DEFAULT_CV_SEED,
    wl_steps: int = _DEFAULT_WL_STEPS,
    wl_check_period: int = _DEFAULT_WL_CHECK_PERIOD,
    wl_update_period: int = _DEFAULT_WL_UPDATE_PERIOD,
    wl_seed: int = _DEFAULT_WL_SEED,
    wl_convergence_threshold: float = _DEFAULT_WL_CONVERGENCE_THRESHOLD,
    initial_bin_width: float = _DEFAULT_BIN_WIDTH,
    min_bins: int = _DEFAULT_MIN_BINS,
    max_bins: int = _DEFAULT_MAX_BINS,
    max_bin_refinements: int = _DEFAULT_MAX_BIN_REFINEMENTS,
    max_wl_blocks: int = _DEFAULT_MAX_WL_BLOCKS,
) -> DisorderDoc:
    """Train a Cluster Expansion on disordered task documents from one ordered
    material and run Wang-Landau sampling to convergence.

    Args:
        disordered_documents: All DisorderedTaskDoc instances sharing the same
            ordered_task_id, prototype, supercell_diag, and versions.
        ordered_task_doc: The CoreTaskDoc for the parent ordered material.
            Its structure is used to populate search metadata (chemsys,
            elements, composition, symmetry, etc.).
        basis_spec: CE basis specification (cutoffs, basis type).
        regularization: Regularization settings for the CE fit.
        weighting: Optional weighting scheme for the CE fit.
        cv_seed: Random seed for cross-validation folds.
        wl_steps: Number of MC steps per WL block.
        wl_check_period: How often (in steps) to check WL flatness.
        wl_update_period: Update period for the WL modification factor.
        wl_seed: Random seed for WL sampling.
        wl_convergence_threshold: Stop when mod_factor drops below this.
        initial_bin_width: Starting energy bin width for WL sampling.
        min_bins: Minimum acceptable number of WL bins (halve bin_width if fewer).
        max_bins: Maximum acceptable number of WL bins (double bin_width if more).
        max_bin_refinements: Maximum bin-width adjustment iterations.
        max_wl_blocks: Maximum convergence blocks before stopping.

    Returns:
        A fully populated DisorderDoc.
    """
    if not disordered_documents:
        raise ValueError("disordered_documents must be non-empty.")

    if basis_spec is None:
        basis_spec = dict(_DEFAULT_BASIS_SPEC)
    if regularization is None:
        regularization = dict(_DEFAULT_REGULARIZATION)
    if weighting is None:
        weighting = dict(_DEFAULT_WEIGHTING)

    # --- validate consistency across documents ---
    first = disordered_documents[0]
    for attr, msg in {
        "ordered_task_id": "Ordered task IDs do not match across documents.",
        "supercell_diag": "Supercell diagonals do not match across documents.",
        "prototype": "Prototypes do not match across documents.",
        "prototype_params": "Prototype parameters do not match across documents.",
        "versions": "Versions do not match across documents.",
    }.items():
        if any(getattr(doc, attr) != getattr(first, attr) for doc in disordered_documents[1:]):
            raise ValueError(msg)

    # --- extract training data ---
    structures_pm = [doc.reference_structure for doc in disordered_documents]
    n_prims = int(np.prod(first.supercell_diag))
    y_cell = [doc.output.energy / float(n_prims) for doc in disordered_documents]

    prototype_spec = PrototypeSpec(
        prototype=first.prototype, params=first.prototype_params
    )

    # The primitive cell uses placeholder element symbols (e.g. "Es", "Fm")
    # for active sublattices, while DisorderedTaskDoc.composition_map uses
    # sublattice labels (e.g. "A", "B").  Build the mapping to translate.
    prim = prototype_spec.primitive_cell
    sublattice_labels = prim.get_array("sublattice")
    chem_symbols = prim.get_chemical_symbols()
    active_subs = prototype_spec.active_sublattices
    # element_symbol -> sublattice_label  (e.g. "Es" -> "A")
    elem_to_label: dict[str, str] = {}
    for sym, lab in zip(chem_symbols, sublattice_labels):
        if sym in active_subs and sym not in elem_to_label:
            elem_to_label[sym] = str(lab)
    # sublattice_label -> element_symbol  (e.g. "A" -> "Es")
    label_to_elem = {v: k for k, v in elem_to_label.items()}

    # Remap composition maps from sublattice labels to element symbols
    composition_maps = [
        {label_to_elem.get(site, site): comp for site, comp in doc.composition_map.items()}
        for doc in disordered_documents
    ]
    sublattices = sublattices_from_composition_maps(composition_maps)

    # --- train cluster expansion ---
    ce_train_output = run_train_ce(
        structures_pm=structures_pm,
        y_cell=y_cell,
        prototype_spec=prototype_spec,
        supercell_diag=first.supercell_diag,
        sublattices=sublattices,
        basis_spec=basis_spec,
        regularization=regularization,
        weighting=weighting,
        cv_seed=cv_seed,
    )

    # --- build ensemble from trained CE ---
    ce = ClusterExpansion.from_dict(ce_train_output.payload)
    ensemble = Ensemble.from_cluster_expansion(
        ce, supercell_matrix=np.diag(first.supercell_diag)
    )

    # --- auto-tune bin width ---
    bin_width = initial_bin_width
    wl_spec = WLSpecParams(
        bin_width=bin_width,
        steps=wl_steps,
        initial_comp_map=composition_maps[0],
        step_type="swap",
        check_period=wl_check_period,
        update_period=wl_update_period,
        seed=wl_seed,
        samples_per_bin=0,
        collect_cation_stats=False,
        production_mode=False,
        reject_cross_sublattice_swaps=False,
    )
    wl_block = run_wl_block(
        spec=wl_spec,
        ensemble=ensemble,
        tip=None,
        prototype_spec=prototype_spec,
        supercell_diag=first.supercell_diag,
    )

    num_bins = len(wl_block["state"].bin_indices)
    for _ in range(max_bin_refinements):
        if min_bins <= num_bins <= max_bins:
            break
        if num_bins < min_bins:
            bin_width /= 2.0
        else:
            bin_width *= 2.0
        wl_spec = WLSpecParams(
            bin_width=bin_width,
            steps=wl_steps,
            initial_comp_map=composition_maps[0],
            step_type="swap",
            check_period=wl_check_period,
            update_period=wl_update_period,
            seed=wl_seed,
            samples_per_bin=0,
            collect_cation_stats=False,
            production_mode=False,
            reject_cross_sublattice_swaps=False,
        )
        wl_block = run_wl_block(
            spec=wl_spec,
            ensemble=ensemble,
            tip=None,
            prototype_spec=prototype_spec,
            supercell_diag=first.supercell_diag,
        )
        num_bins = len(wl_block["state"].bin_indices)
    else:
        raise RuntimeError(
            f"Bin-width tuning did not converge after {max_bin_refinements} "
            f"refinements (num_bins={num_bins}, target=[{min_bins}, {max_bins}])."
        )

    # --- WL convergence loop ---
    for _ in range(max_wl_blocks):
        if wl_block["state"].mod_factor <= wl_convergence_threshold:
            break
        wl_block = run_wl_block(
            spec=wl_spec,
            ensemble=ensemble,
            tip=wl_block,
            prototype_spec=prototype_spec,
            supercell_diag=first.supercell_diag,
        )
    else:
        raise RuntimeError(
            f"WL convergence not reached after {max_wl_blocks} blocks "
            f"(mod_factor={wl_block['state'].mod_factor}, "
            f"threshold={wl_convergence_threshold})."
        )

    # --- Production-mode block to collect cation stats ---
    prod_spec = WLSpecParams(
        bin_width=bin_width,
        steps=wl_steps,
        initial_comp_map=composition_maps[0],
        step_type="swap",
        check_period=wl_check_period,
        update_period=wl_update_period,
        seed=wl_seed,
        samples_per_bin=0,
        collect_cation_stats=True,
        production_mode=True,
        reject_cross_sublattice_swaps=False,
    )
    prod_block = run_wl_block(
        spec=prod_spec,
        ensemble=ensemble,
        tip=wl_block,
        prototype_spec=prototype_spec,
        supercell_diag=first.supercell_diag,
    )

    # --- assemble DisorderDoc ---
    wl_final = prod_block["state"]
    return DisorderDoc.from_structure(
        meta_structure=ordered_task_doc.structure,
        ordered_task_id=first.ordered_task_id,
        prototype=first.prototype,
        prototype_params=first.prototype_params,
        supercell_diag=first.supercell_diag,
        sublattices=sublattices,
        composition_maps=composition_maps,
        training_stats=ce_train_output.stats,
        design_metrics=ce_train_output.design_metrics,
        wl_dos=WLDensityOfStates(
            bin_indices=wl_final.bin_indices,
            entropy=wl_final.entropy,
            bin_size=wl_final.bin_size,
            mod_factor=wl_final.mod_factor,
            steps_counter=wl_final.steps_counter,
        ),
        wl_occupancy=list(prod_block["occupancy"]),
        wl_spec_params=wl_spec,
        cation_counts=[
            CationBinCount(**row) for row in prod_block["cation_counts"]
        ],
        disordered_task_ids=[doc.task_id for doc in disordered_documents],
        versions=first.versions,
    )
