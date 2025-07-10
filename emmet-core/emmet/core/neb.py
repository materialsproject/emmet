"""Schemas and utils for NEB calculations."""

from __future__ import annotations

from datetime import datetime
import numpy as np
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from scipy.interpolate import CubicSpline
from typing import TYPE_CHECKING, Any
from typing_extensions import Self

from monty.os.path import zpath
from pymatgen.core import Structure, Molecule

from emmet.core.tasks import (
    _VOLUMETRIC_FILES,
    _find_vasp_files,
    _parse_custodian,
    _parse_orig_inputs,
    InputDoc,
    CustodianDoc,
    OrigInputs,
)
from emmet.core.utils import ValueEnum, utcnow
from emmet.core.vasp.calculation import Calculation, VaspObject
from emmet.core.vasp.task_valid import TaskState

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray


class NebMethod(ValueEnum):
    """Common methods for NEB calculations.

    TODO: convert to StrEnum
    """

    STANDARD = "standard"
    CLIMBING_IMAGE = "climbing_image"
    APPROX = "approx_neb"


class HopFailureReason(ValueEnum):
    """Define failure modes for ApproxNEB calculations."""

    ENDPOINT = "Endpoint structure relaxation failed."
    MIN_DIST = "Linear distance traversed by working ion is below threshold."
    MIN_IMAGE = "Too few image calculations succeeded."
    IMAGE_FAILURE = "No image calculation output."


class BarrierAnalysis(BaseModel):
    """Define analysis schema for barrier calculations."""

    energies: list[float] = Field(
        description="The energies of each frame along the reaction coordinate."
    )
    frame_index: list[float] | None = Field(
        None,
        description="The fractional index along the reaction coordinate, between 0 and 1.",
    )
    cubic_spline_pars: list[list[float]] | None = Field(
        None, description="Parameters of the cubic spline used to fit the energies."
    )
    ts_frame_index: float | None = Field(
        None, description="The fractional index of the reaction coordinate."
    )
    ts_energy: float | None = Field(
        None, description="The energy at the transition state."
    )
    ts_in_frames: bool | None = Field(
        None,
        description="Whether the transition state is one of the computed snapshots.",
    )
    forward_barrier: float | None = Field(None, description="The forward barrier.")
    reverse_barrier: float | None = Field(None, description="The reverse barrier.")

    @classmethod
    def from_energies(
        cls,
        energies: Sequence[float],
        frame_index: Sequence[float] | NDArray | None = None,
        spline_kwargs: dict[str, Any] | None = None,
        frame_match_tol: float = 1.0e-6,
    ) -> Self:
        """
        Define basic NEB analysis tools.

        Parameters
        ----------
        energies : Sequence of float
            The energies sorted by increasing frame index. Must include endpoints.
        frame_index : Sequence of float or None (default)
            If None, defaults to a linear interpolation between 0 and 1 for each
            energy in energies. If not None, specifies the indices of succcessful
            images.
        spline_kwargs : dict or None
            The kwargs to pass to the spline fit. Defaults to clamping the derivative
            to zero at the endpoints, consistent with the assumption that they
            represent minima along the potential energy surface.
        frame_match_tol : float = 1.e-6
            The tolerance for matching the transition state frame index to the
            input frame indices.
        """
        frame_index = frame_index or list(range(len(energies)))
        frame_index = np.array(frame_index) / max(frame_index)

        analysis: dict[str, Any] = {
            "energies": list(energies),
            "frame_index": list(frame_index),
        }
        energies = np.array(energies)  # type: ignore[assignment]

        spline_kwargs = spline_kwargs or {"bc_type": "clamped"}
        spline_fit = CubicSpline(frame_index, energies, **spline_kwargs)
        analysis["cubic_spline_pars"] = spline_fit.c.tolist()

        crit_points = spline_fit.derivative().roots(extrapolate=False)
        analysis["ts_frame_index"] = -1
        analysis["ts_energy"] = -np.inf
        for crit_point in crit_points:
            if (energy := spline_fit(crit_point)) > analysis[
                "ts_energy"
            ] and spline_fit(crit_point, 2) <= 0.0:
                analysis["ts_frame_index"] = crit_point
                analysis["ts_energy"] = float(energy)

        analysis["ts_in_frames"] = any(
            abs(analysis["ts_frame_index"] - idx)
            < frame_match_tol * max(idx, frame_match_tol)
            for idx in frame_index
        )
        analysis["forward_barrier"] = analysis["ts_energy"] - energies[0]
        analysis["reverse_barrier"] = analysis["ts_energy"] - energies[-1]

        return cls(**analysis)


class NebResult(BaseModel):
    """Container class to store high-level NEB calculation info.

    This is intended to be code-agnostic, whereas NebTaskDoc
    is VASP-specific.
    """

    images: list[Structure | Molecule] | None = Field(
        None,
        description=(
            "Relaxed structures/molecules along the reaction pathway, "
            "including endpoints."
        ),
    )

    initial_images: list[Structure | Molecule] | None = Field(
        None, description="Unrelaxed structures/molecules along the reaction pathway."
    )

    image_indices: list[int] | None = Field(
        None,
        description="The indexes corresponding to initial_images of all successful image calculations.",
    )

    energies: list[float] | None = Field(
        None, description="Energies corresponding the structures in `images`."
    )

    dir_name: str | None = Field(
        None, description="Top-level NEB calculation directory."
    )

    state: TaskState | None = Field(
        None, description="Whether the NEB calculation succeeded."
    )

    neb_method: NebMethod | None = Field(
        None, description="The NEB method used for this calculation."
    )

    forward_barrier: float | None = Field(
        None,
        description=(
            "Forward barrier for this reaction, "
            "i.e., the transition state energy minus "
            "the reactant / initial configuration energy."
        ),
    )

    reverse_barrier: float | None = Field(
        None,
        description=(
            "Reverse barrier for this reaction, "
            "i.e., the transition state energy minus "
            "the product / final configuration energy."
        ),
    )

    barrier_analysis: BarrierAnalysis | None = Field(
        None, description="Analysis of the reaction barrier."
    )

    failure_reasons: list[HopFailureReason] | None = Field(
        None, description="Reasons why the barrier calculation failed."
    )

    tags: list[str] | None = Field(
        None, description="List of string metadata about the calculation."
    )

    identifier: str | None = Field(None, description="Identifier for the calculation.")

    @model_validator(mode="after")
    def set_barriers(self) -> Self:
        """Perform analysis on barrier if needed."""
        if (
            (not self.forward_barrier or not self.reverse_barrier)
            and isinstance(self.energies, list)
            and len(self.energies) > 0
        ):
            self.barrier_analysis = BarrierAnalysis.from_energies(
                self.energies, frame_index=self.image_indices
            )
            for k in ("forward", "reverse"):
                setattr(
                    self,
                    f"{k}_barrier",
                    getattr(self.barrier_analysis, f"{k}_barrier", None),
                )
        return self

    @property
    def barrier_energy_range(self) -> float | None:
        """The maximum computed energy minus the minimum computed energy along the path."""
        if self.energies:
            return max(self.energies) - min(self.energies)
        return None  # mypy is not happy with implicit `None` return


class NebTaskDoc(NebResult):
    """Define schema for VASP NEB tasks."""

    endpoint_structures: list[Structure] = Field(
        description="The initial and final configurations (reactants and products) of the barrier.",
    )
    endpoint_energies: list[float] | None = Field(
        None, description="Energies of the endpoint structures."
    )
    endpoint_calculations: list[Calculation] | None = Field(
        None, description="Calculation information for the endpoint structures"
    )
    endpoint_objects: list[dict[VaspObject, Any]] | None = Field(
        None, description="VASP objects for each endpoint calculation."
    )
    endpoint_directories: list[str] | None = Field(
        None, description="List of the directories for the endpoint calculations."
    )

    image_structures: list[Structure] | None = Field(
        None, description="Final structures for each NEB images."
    )
    image_energies: list[float] | None = Field(
        None, description="Final energies for each image"
    )
    image_calculations: list[Calculation] | None = Field(
        None, description="Full calculation output for the NEB images."
    )

    image_directories: list[str] | None = Field(
        None, description="List of the directories where the NEB images are located"
    )
    image_objects: dict[int, dict[VaspObject, Any]] | None = Field(
        None, description="VASP objects for each image calculation."
    )

    orig_inputs: OrigInputs | None = Field(
        None,
        description="The exact set of input parameters used to generate the current task document.",
    )

    inputs: InputDoc | None = Field(
        None, description="Inputs used in this calculation."
    )

    custodian: list[CustodianDoc] | None = Field(
        None,
        description="Detailed custodian data for each VASP calculation contributing to the task document.",
    )

    last_updated: datetime | None = Field(
        utcnow(),
        description="Timestamp for the most recent calculation for this task document",
    )

    completed_at: datetime | None = Field(
        None, description="Timestamp for when this task was completed"
    )

    task_label: str | None = Field(
        None, description="Label for the NEB calculation(s)."
    )

    def model_post_init(self, __context: Any) -> None:
        """Ensure base model fields are populated for analysis."""

        if self.energies is None:
            if self.endpoint_energies is not None:
                self.energies = [  # type: ignore[misc]
                    self.endpoint_energies[0],
                    *self.image_energies,
                    self.endpoint_energies[1],
                ]
            else:
                self.energies = self.image_energies

        self.images = self.images or [
            self.endpoint_structures[0],
            *(self.image_structures or []),
            self.endpoint_structures[1],
        ]

        if self.initial_images is None:
            if self.endpoint_calculations:
                ep_structures = [
                    calc.input.structure for calc in self.endpoint_calculations
                ]
            else:
                ep_structures = self.endpoint_structures

            intermed_structs = []
            if self.image_calculations:
                intermed_structs = [
                    calc.input.structure for calc in self.image_calculations
                ]

            self.initial_images = [
                ep_structures[0],
                *intermed_structs,
                ep_structures[1],
            ]

    @property
    def num_images(self) -> int | None:
        return len(self.image_structures) if self.image_structures else None

    @classmethod
    def from_directory(
        cls,
        dir_name: str | Path,
        volumetric_files: Sequence[str] = _VOLUMETRIC_FILES,
        store_calculations: bool = True,
        **neb_task_doc_kwargs,
    ) -> Self:
        """
        Return an NebTaskDoc from a single NEB calculation directory.

        This method populates only the image energies and calculations fields,
        and the endpoint structures.
        """
        if isinstance(dir_name, str):
            dir_name = Path(dir_name)

        neb_directories = sorted(dir_name.glob("[0-9][0-9]"))

        if (ep_calcs := neb_task_doc_kwargs.pop("endpoint_calculations", None)) is None:
            endpoint_directories = [neb_directories[0], neb_directories[-1]]
            endpoint_structures = [
                Structure.from_file(zpath(f"{endpoint_dir}/POSCAR"))
                for endpoint_dir in endpoint_directories
            ]
            endpoint_energies = None
        else:
            endpoint_directories = neb_task_doc_kwargs.pop("endpoint_directories")
            endpoint_structures = [ep_calc.output.structure for ep_calc in ep_calcs]
            endpoint_energies = [ep_calc.output.energy for ep_calc in ep_calcs]

        image_directories = neb_directories[1:-1]

        image_calculations = []
        image_structures = []
        image_objects = {}
        for iimage, image_dir in enumerate(image_directories):
            vasp_files = _find_vasp_files(image_dir, volumetric_files=volumetric_files)

            calc, image_objects[iimage] = Calculation.from_vasp_files(
                dir_name=image_dir,
                task_name=f"NEB image {iimage + 1}",
                vasprun_file=vasp_files["standard"]["vasprun_file"],
                outcar_file=vasp_files["standard"]["outcar_file"],
                contcar_file=vasp_files["standard"]["contcar_file"],
                volumetric_files=vasp_files["standard"].get("volumetric_files", []),
                oszicar_file=vasp_files["standard"].get("oszicar_file", None),
                vasprun_kwargs={
                    "parse_potcar_file": False,
                },
            )
            image_calculations.append(calc)
            image_structures.append(calc.output.structure)

        calcs_to_check = image_calculations + (ep_calcs or [])

        task_state = (
            TaskState.SUCCESS
            if all(
                calc.has_vasp_completed == TaskState.SUCCESS for calc in calcs_to_check
            )
            else TaskState.FAILED
        )

        inputs = {}
        for suffix in (None, ".orig"):
            vis = {
                k.lower(): v
                for k, v in _parse_orig_inputs(dir_name, suffix=suffix).items()
            }
            if (potcar_spec := vis.get("potcar")) is not None:
                vis["potcar_spec"] = potcar_spec
                vis["potcar"] = [spec.titel for spec in potcar_spec]

            if suffix is None:
                inputs["inputs"] = InputDoc(
                    **vis, magnetic_moments=vis.get("incar", {}).get("MAGMOM")
                )
            else:
                inputs["orig_inputs"] = OrigInputs(**vis)

        neb_method = (
            NebMethod.CLIMBING_IMAGE
            if inputs["inputs"].incar.get("LCLIMB", False)
            else NebMethod.STANDARD
        )

        return cls(
            endpoint_structures=endpoint_structures,
            endpoint_energies=endpoint_energies,
            endpoint_directories=[str(ep_dir) for ep_dir in endpoint_directories],
            endpoint_calculations=ep_calcs if store_calculations else None,
            image_calculations=image_calculations if store_calculations else None,
            image_structures=image_structures,
            dir_name=str(dir_name),
            image_directories=[str(img_dir) for img_dir in image_directories],
            orig_inputs=inputs["orig_inputs"],
            inputs=inputs["inputs"],
            image_objects=image_objects,
            neb_method=neb_method,  # type: ignore[arg-type]
            state=task_state,
            image_energies=[calc.output.energy for calc in image_calculations],
            custodian=_parse_custodian(dir_name),
            completed_at=max(calc.completed_at for calc in calcs_to_check),
            **neb_task_doc_kwargs,
        )

    @classmethod
    def from_directories(
        cls,
        endpoint_directories: list[str | Path],
        neb_directory: str | Path,
        volumetric_files: Sequence[str] = _VOLUMETRIC_FILES,
        **neb_task_doc_kwargs,
    ) -> Self:
        """
        Return an NebTaskDoc from endpoint and NEB calculation directories.

        This method populates the endpoint and image fields completely,
        permitting an analysis of the barrier.
        """
        endpoint_calculations = [None for _ in range(2)]
        endpoint_objects = [None for _ in range(2)]
        for idx, endpoint_dir in enumerate(endpoint_directories):
            vasp_files = _find_vasp_files(
                endpoint_dir, volumetric_files=volumetric_files
            )
            ep_key = (
                "standard"
                if vasp_files.get("standard")
                else "relax"
                + str(
                    max(
                        int(k.split("relax")[-1])
                        for k in vasp_files
                        if k.startswith("relax")
                    )
                )
            )

            (
                endpoint_calculations[idx],
                endpoint_objects[idx],
            ) = Calculation.from_vasp_files(
                dir_name=endpoint_dir,
                task_name=f"NEB endpoint {idx + 1}",
                vasprun_file=vasp_files[ep_key]["vasprun_file"],
                outcar_file=vasp_files[ep_key]["outcar_file"],
                contcar_file=vasp_files[ep_key]["contcar_file"],
                volumetric_files=vasp_files[ep_key].get("volumetric_files", []),
                oszicar_file=vasp_files[ep_key].get("oszicar_file", None),
                vasprun_kwargs={
                    "parse_potcar_file": False,
                },
            )

        return cls.from_directory(
            neb_directory,
            volumetric_files=volumetric_files,
            endpoint_calculations=endpoint_calculations,
            endpoint_objects=endpoint_objects,
            endpoint_directories=endpoint_directories,
            **neb_task_doc_kwargs,
        )


class NebPathwayResult(BaseModel):  # type: ignore[call-arg]
    """Class for containing multiple NEB calculations, as along a reaction pathway."""

    hops: dict[str, NebResult] = Field(
        description="Dict of NEB calculations included in this calculation"
    )

    forward_barriers: dict[str, float | None] | None = Field(
        None, description="Dict of the forward barriers computed here."
    )

    reverse_barriers: dict[str, float | None] | None = Field(
        None, description="Dict of the reverse barriers computed here."
    )

    identifier: str | None = Field(None, description="Identifier for the calculation.")

    tags: list[str] | None = Field(
        None, description="List of string metadata about the calculation."
    )

    host_structure: Structure | None = Field(
        None, description="The structure without active/mobile site(s)."
    )

    host_formula: str | None = Field(
        None,
        description="The chemical formula of the structure without active site(s).",
    )

    host_formula_reduced: str | None = Field(
        None,
        description="The reduced chemical formula of the structure without active site(s).",
    )

    host_chemsys: str | None = Field(
        None,
        description="The chemical system for the structure without active site(s).",
    )

    active_species: str | None = Field(
        None, description="The formula of the active/mobile species."
    )

    @model_validator(mode="after")
    def set_top_levels(self) -> Self:
        """Set barriers and host structure metadata, if needed."""
        for direction in ("forward", "reverse"):
            if getattr(self, f"{direction}_barriers", None) is None:
                setattr(
                    self,
                    f"{direction}_barriers",
                    {
                        idx: getattr(neb_calc, f"{direction}_barrier", None)
                        for idx, neb_calc in self.hops.items()
                    },
                )

        if self.host_structure is not None:
            self.host_formula = self.host_structure.formula
            self.host_formula_reduced = self.host_structure.reduced_formula
            self.host_chemsys = self.host_structure.chemical_system

        return self

    @property
    def max_barriers(self) -> dict[str, float | None] | None:
        """Retrieve the maximum barrier along each hop."""

        barriers: dict[str, list[float]] = {}
        for b in [self.forward_barriers, self.reverse_barriers]:
            if b:
                for idx, barrier in b.items():
                    if barrier:
                        if idx not in barriers:
                            barriers[idx] = []
                        barriers[idx].append(barrier)

        if len(barriers) == 0:
            return None

        return {idx: max(v) for idx, v in barriers.items()}

    @property
    def barrier_ranges(self) -> dict[str, float | None]:
        """Retrieve the max minus min computed energy along each hop."""
        return {
            idx: neb_calc.barrier_energy_range for idx, neb_calc in self.hops.items()
        }
