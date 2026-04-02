from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure
from typing_extensions import Self, TypedDict
from ulid import ULID

from emmet.core.material_property import PropertyDoc
from emmet.core.tasks import _VOLUMETRIC_FILES, CoreTaskDoc
from emmet.core.trajectory import RelaxTrajectory
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.typing import IdentifierType

REQUIRED_METADATA_KEYS: tuple[str, ...] = (
    "ordered_task_id",
    "reference_structure",
    "supercell_diag",
    "prototype",
    "prototype_params",
    "composition_map",
    "versions",
)


class TypedDisorderedTaskMetadata(TypedDict):
    ordered_task_id: IdentifierType
    reference_structure: Structure
    supercell_diag: tuple[int, int, int]
    prototype: str
    prototype_params: dict[str, float]
    composition_map: dict[str, dict[str, int]]
    versions: dict[str, str]


def parse_json(dir_name: Path | str) -> TypedDisorderedTaskMetadata:
    """Parse the disordered_task_doc_metadata.json file from the given directory."""
    dir_path = Path(dir_name)
    json_file = dir_path / "disordered_task_doc_metadata.json"

    if not json_file.exists():
        raise FileNotFoundError(
            f"No disordered_task_doc_metadata.json found in directory: {dir_name}"
        )

    with json_file.open("r") as f:
        data = json.load(f)

    missing_keys = [key for key in REQUIRED_METADATA_KEYS if key not in data]
    if missing_keys:
        missing_str = ", ".join(missing_keys)
        raise ValueError(
            f"Missing required keys in disordered_task_doc_metadata.json: {missing_str}"
        )

    supercell_x, supercell_y, supercell_z = data["supercell_diag"]
    data["supercell_diag"] = (supercell_x, supercell_y, supercell_z)
    data["reference_structure"] = Structure.from_dict(data["reference_structure"])
    return data


# ---------------------------------------------------------------------------
# CE training sub-models
# ---------------------------------------------------------------------------


class CEFitMetrics(BaseModel):
    """Per-site error metrics for a single CE evaluation (in-sample or CV)."""

    n: int = Field(..., description="Number of structures in this group.")
    mae_per_site: float = Field(..., description="Mean absolute error per site.")
    rmse_per_site: float = Field(..., description="Root-mean-square error per site.")
    max_abs_per_site: float = Field(..., description="Maximum absolute error per site.")


class CECompositionStats(BaseModel):
    """In-sample and CV metrics for a single composition group."""

    in_sample: CEFitMetrics = Field(...)
    five_fold_cv: CEFitMetrics = Field(...)


class CETrainingStats(BaseModel):
    """Full CE training statistics: aggregate + per-composition breakdown."""

    in_sample: CEFitMetrics = Field(..., description="In-sample fit metrics (all compositions).")
    five_fold_cv: CEFitMetrics = Field(..., description="5-fold CV metrics (all compositions).")
    by_composition: dict[str, CECompositionStats] = Field(
        ..., description="Per-composition metrics keyed by composition signature."
    )


class CEDesignMetrics(BaseModel):
    """Design-matrix diagnostics for CE training."""

    n_samples: int = Field(..., description="Number of training structures.")
    n_features: int = Field(..., description="Number of CE features (correlation functions).")
    rank: int = Field(..., description="Numerical rank of the design matrix.")
    sigma_max: float = Field(..., description="Largest singular value.")
    sigma_min: float = Field(..., description="Smallest nonzero singular value.")
    condition_number: float = Field(..., description="Condition number (sigma_max / sigma_min).")
    logdet_xtx: float = Field(..., description="Log-determinant of X^T X (D-optimality).")
    leverage_mean: float = Field(..., description="Mean leverage (hat-matrix diagonal).")
    leverage_max: float = Field(..., description="Maximum leverage.")
    leverage_p95: float = Field(..., description="95th percentile leverage.")
    weighting_applied: bool = Field(..., description="Whether sample weighting was used.")
    standardization: Literal["none", "column_zscore"] = Field(
        ..., description="Column standardization mode applied before SVD."
    )
    zero_variance_feature_count: int = Field(
        ..., description="Number of features with zero variance."
    )


# ---------------------------------------------------------------------------
# Wang-Landau sub-models
# ---------------------------------------------------------------------------


class WLDensityOfStates(BaseModel):
    """Converged Wang-Landau density of states.

    Stores only the fields needed to compute thermodynamics (partition function,
    free energy, heat capacity, transition temperature) plus convergence quality
    indicators.  Energy for bin *i* is ``bin_indices[i] * bin_size``.
    """

    bin_indices: list[int] = Field(..., description="Sorted energy-bin indices visited during sampling.")
    entropy: list[float] = Field(..., description="Log-DOS estimate per visited bin (parallel to bin_indices).")
    bin_size: float = Field(..., description="Energy bin width for converting indices to energies.")
    mod_factor: float = Field(..., description="Final Wang-Landau modification factor (convergence indicator).")
    steps_counter: int = Field(..., description="Total MC steps elapsed during sampling.")


class WLSpecParams(BaseModel):
    """Parameters that fully specify a Wang-Landau sampling run."""

    bin_width: float = Field(..., description="Energy bin width (eV / prim).")
    steps: int = Field(..., description="MC steps per WL block.")
    initial_comp_map: dict[str, dict[str, int]] = Field(
        ..., description="Initial composition map for occupancy initialisation."
    )
    step_type: str = Field(..., description="MC step type, e.g. 'swap'.")
    check_period: int = Field(..., description="Steps between flatness checks.")
    update_period: int = Field(..., description="Steps between modification-factor updates.")
    seed: int = Field(..., description="Random seed for MC sampling.")
    samples_per_bin: int = Field(..., description="Unique occupancy samples to capture per bin.")
    collect_cation_stats: bool = Field(..., description="Whether per-bin cation counts were collected.")
    production_mode: bool = Field(..., description="Whether WL updates were frozen (production mode).")
    reject_cross_sublattice_swaps: bool = Field(
        ..., description="Whether cross-sublattice swaps were rejected."
    )


class CationBinCount(BaseModel):
    """One entry in the per-bin cation-count histogram from production WL sampling.

    Each row records how many times a particular (bin, sublattice, element, n_sites)
    combination was observed during the production-mode WL run.  Together the full
    list of entries encodes the information needed to compute composition-vs-energy
    x(E), canonical composition x(T), and sublattice purity(T).
    """

    bin: int = Field(..., description="Energy-bin index.")
    sublattice: str = Field(..., description="Sublattice placeholder label (e.g. 'Es').")
    element: str = Field(..., description="Element symbol (e.g. 'Al').")
    n_sites: int = Field(..., description="Number of sublattice sites occupied by this element in the sampled microstate.")
    count: int = Field(..., description="Number of times this (bin, sublattice, element, n_sites) was observed.")


class DisorderedTaskDoc(CoreTaskDoc):
    """Document for a disordered structure task, extending the CoreTaskDoc with additional metadata to
    capture disorder-specific information and its relationship to the ordered structure.
    """

    task_id: str = Field(
        default_factory=lambda: str(ULID()),
        description="Auto-generated ULID for this disordered task.",
    )

    ordered_task_id: IdentifierType = Field(
        ...,
        description="The task ID of the ordered structure task from which this disordered structure was generated.",
    )
    reference_structure: StructureType = Field(
        ...,
        description="The reference disordered structure used to start relaxation and represent this disordered structure in the cluster expansion.",
    )
    supercell_diag: tuple[int, int, int] = Field(
        ...,
        description="The supercell diagonal used to generate this disordered structure from the prototype structure.",
    )
    prototype: str = Field(
        ...,
        description="The prototype name from which this disordered structure was generated.",
    )
    prototype_params: dict[str, float] = Field(
        ...,
        description="The parameters used to generate the prototype structure.",
    )
    composition_map: dict[str, dict[str, int]] = Field(
        ...,
        description="A mapping of which elements are in each sublattice for the disordered structure.",
    )
    versions: dict[str, str] = Field(
        ...,
        description="A dictionary capturing the versions of relevant software packages used during the calculation.",
    )

    @classmethod
    def from_directory(
        cls,
        dir_name: Path | str,
        volumetric_files: tuple[str, ...] = _VOLUMETRIC_FILES,
        **vasp_calculation_kwargs,
    ) -> tuple[Self, RelaxTrajectory]:
        base_doc, trajectory = CoreTaskDoc.from_directory(
            dir_name,
            volumetric_files=volumetric_files,
            **vasp_calculation_kwargs,
        )

        metadata = parse_json(dir_name)

        data = base_doc.model_dump()
        # Remove None task_id so the ULID default_factory can populate it
        if data.get("task_id") is None:
            data.pop("task_id", None)
        data.update(
            ordered_task_id=metadata["ordered_task_id"],
            reference_structure=metadata["reference_structure"],
            supercell_diag=tuple(metadata["supercell_diag"]),
            prototype=metadata["prototype"],
            prototype_params=metadata["prototype_params"],
            composition_map=metadata["composition_map"],
            versions=metadata["versions"],
        )

        return (cls.model_validate(data), trajectory)


class DisorderDoc(PropertyDoc):
    """Aggregated disorder document produced by training a cluster expansion
    on a set of :class:`DisorderedTaskDoc` instances from one ordered material
    and running Wang-Landau sampling to derive the density of states.

    Stores the raw CE and WL results; derived thermodynamics (free energy,
    heat capacity, transition temperature) are computed downstream.
    """

    property_name: str = "disorder"

    # ---- identity ----
    ordered_task_id: IdentifierType = Field(
        ...,
        description="The task ID of the parent ordered structure.",
    )

    # ---- system description ----
    prototype: str = Field(
        ...,
        description="Prototype name, e.g. 'spinel_Q0O'.",
    )
    prototype_params: dict[str, float] = Field(
        ...,
        description="Geometry parameters used to build the prototype cell.",
    )
    supercell_diag: tuple[int, int, int] = Field(
        ...,
        description="Supercell diagonal used for CE training / WL sampling.",
    )
    sublattices: dict[str, tuple[str, ...]] = Field(
        ...,
        description="Mapping of sublattice placeholder to allowed species, "
        "e.g. {'Es': ('Al', 'Mg'), 'Fm': ('Al', 'Mg')}.",
    )
    composition_maps: list[dict[str, dict[str, int]]] = Field(
        ...,
        description="Per-task composition maps (sublattice -> element -> count).",
    )

    # ---- cluster expansion results ----
    training_stats: CETrainingStats = Field(
        ...,
        description="CE fit statistics: in-sample, 5-fold CV, and per-composition.",
    )
    design_metrics: CEDesignMetrics = Field(
        ...,
        description="Design-matrix diagnostics (rank, condition number, leverage, etc.).",
    )

    # ---- Wang-Landau results ----
    wl_dos: WLDensityOfStates = Field(
        ...,
        description="Converged Wang-Landau density of states.",
    )
    wl_occupancy: list[int] = Field(
        ...,
        description="Encoded site occupancy of the last accepted WL snapshot.",
    )
    wl_spec_params: WLSpecParams = Field(
        ...,
        description="WL sampling specification parameters.",
    )
    cation_counts: list[CationBinCount] = Field(
        ...,
        description="Per-bin cation-count histogram from production-mode WL sampling, "
        "used to compute x(E), x(T), and purity(T).",
    )

    # ---- provenance ----
    disordered_task_ids: list[IdentifierType] = Field(
        ...,
        description="Task IDs of the DisorderedTaskDocs used as CE training data.",
    )
    versions: dict[str, str] = Field(
        ...,
        description="Software versions used during the calculation.",
    )
