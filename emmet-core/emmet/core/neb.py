"""Schemas and utils for NEB calculations."""

from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson
from monty.os.path import zpath
from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)
from pymatgen.core import Molecule, Structure
from scipy.interpolate import CubicSpline
from typing_extensions import Self

from emmet.core.tasks import (
    _VOLUMETRIC_FILES,
    CustodianDoc,
    InputDoc,
    OrigInputs,
    _find_vasp_files,
    _parse_custodian,
    _parse_orig_inputs,
)
from emmet.core.types.enums import ValueEnum, VaspObject
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.utils import arrow_incompatible, type_override
from emmet.core.types.typing import DateTimeType, NullableDateTimeType
from emmet.core.vasp.calculation import Calculation
from emmet.core.vasp.task_valid import TaskState

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from numpy.typing import NDArray


def _join_endpoint_and_image_data(
    endpoint_data: list[Any],
    image_data: list[Any] | None,
    map_fun: Callable | None = None,
) -> list[Any]:
    data = [endpoint_data[0], *(image_data or []), endpoint_data[1]]
    if map_fun:
        data = list(map(map_fun, data))
    return data


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


@arrow_incompatible
class NebResult(BaseModel):
    """Container class to store high-level NEB calculation info.

    This is intended to be code-agnostic, whereas NebTaskDoc
    is VASP-specific.
    """

    images: list[Structure | Molecule] | None = Field(
        None,
        description=(
            "Structures/molecules along the reaction pathway, "
            "including endpoints, after NEB."
        ),
    )

    initial_images: list[Structure | Molecule] | None = Field(
        None,
        description="Structures/molecules along the reaction pathway, prior to NEB.",
    )

    image_indices: list[int] | None = Field(
        None,
        description="The indexes corresponding to initial_images of all successful image calculations.",
    )

    energies: list[float] | None = Field(
        None, description="Energies corresponding the structures in `images`."
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

    dir_name: str | None = Field(
        None, description="Directory where calculation was run."
    )

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
        return None

    @property
    def num_images(self) -> int | None:
        if self.images:
            return len(self.images)
        return None


@type_override({"objects": str})
class NebIntermediateImagesDoc(BaseModel):
    """Schema for high-level intermediate image NEB data."""

    energies: list[float] | None = Field(
        None, description="The final energies of the intermediate images."
    )
    images: list[StructureType] | None = Field(
        None, description="Final structures for each intermediate image."
    )

    initial_images: list[StructureType] | None = Field(
        None, description="The initial intermediate image structures."
    )

    calculations: list[Calculation] | None = Field(
        None, description="Full calculation output for the intermediate images."
    )

    dir_name: str | None = Field(
        None, description="Top-level NEB calculation directory."
    )

    directories: list[str] | None = Field(
        None, description="List of the directories where the NEB images are located."
    )

    state: TaskState | None = Field(
        None, description="Whether the NEB calculation succeeded."
    )
    neb_method: NebMethod | None = Field(
        None, description="The NEB method used for this calculation."
    )

    orig_inputs: OrigInputs | None = Field(
        None,
        description="The exact set of input parameters used to generate the current task document.",
    )

    objects: list[dict[VaspObject, Any]] | None = Field(
        None, description="VASP objects for each image calculation."
    )

    inputs: InputDoc | None = Field(
        None, description="Inputs used in this calculation."
    )

    custodian: list[CustodianDoc] | None = Field(
        None,
        description="Detailed custodian data for each VASP calculation contributing to the task document.",
    )

    completed_at: NullableDateTimeType = Field(
        description="Timestamp for when this task was completed"
    )

    task_label: str | None = Field(
        None, description="Label for the NEB calculation(s)."
    )

    @field_serializer("objects", mode="wrap")
    def objects_serializer(self, d, default_serializer, info):
        default_serialized_object = default_serializer(d, info)

        format = info.context.get("format") if info.context else None
        if format == "arrow":
            return orjson.dumps(default_serialized_object)

        return default_serialized_object

    @field_validator("objects", mode="before")
    def objects_deserializer(cls, d):
        return orjson.loads(d) if isinstance(d, str) else d

    @classmethod
    def from_directory(
        cls,
        dir_name: str | Path,
        volumetric_files: Sequence[str] = _VOLUMETRIC_FILES,
        store_calculations: bool = True,
        **kwargs,
    ) -> Self:
        """
        Return an NebTaskDoc from a single NEB calculation directory.

        This method populates only the image energies and calculations fields,
        and the endpoint structures.
        """
        if isinstance(dir_name, str):
            dir_name = Path(dir_name)

        neb_directories = sorted(dir_name.glob("[0-9][0-9]"))

        image_directories = neb_directories[1:-1]

        image_calculations = []
        initial_structures = []
        image_structures = []
        image_objects = []
        for iimage, image_dir in enumerate(image_directories):
            vasp_files = _find_vasp_files(image_dir, volumetric_files=volumetric_files)

            calc, objects = Calculation.from_vasp_files(
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
            initial_structures.append(calc.input.structure)
            image_objects.append(objects)

        task_state = (
            TaskState.SUCCESS
            if all(
                calc.has_vasp_completed == TaskState.SUCCESS
                for calc in image_calculations
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
            calculations=image_calculations if store_calculations else None,
            images=image_structures,
            initial_images=initial_structures,
            dir_name=str(dir_name),
            directories=[str(img_dir) for img_dir in image_directories],
            orig_inputs=inputs["orig_inputs"],
            inputs=inputs["inputs"],
            objects=image_objects,
            neb_method=neb_method,  # type: ignore[arg-type]
            state=task_state,
            energies=[calc.output.energy for calc in image_calculations],
            custodian=_parse_custodian(dir_name),
            completed_at=max(calc.completed_at for calc in image_calculations),
            **kwargs,
        )


class NebTaskDoc(NebResult):
    """Define schema for VASP NEB tasks."""

    images: list[StructureType] | None = Field(  # type: ignore[assignment]
        None,
        description=(
            "Structures (including endpoints) along the reaction pathway after NEB."
        ),
    )

    initial_images: list[StructureType] | None = Field(  # type: ignore[assignment]
        None,
        description="Structures (including endpoints) along the reaction pathway prior to NEB.",
    )

    directories: list[str] | None = Field(
        None, description="Calculation directories for each image."
    )

    calculations: list[Calculation] | None = Field(
        None, description="The VASP calculations associated with each image."
    )

    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent calculation for this task document",
    )

    objects: list[dict[VaspObject, Any] | None] | None = Field(
        None, description="VASP objects associated with each image calculation."
    )

    @classmethod
    def from_directories(
        cls,
        endpoint_directories: list[str | Path],
        neb_directory: str | Path,
        volumetric_files: Sequence[str] = _VOLUMETRIC_FILES,
        store_calculations: bool = True,
        **kwargs,
    ) -> Self:
        """
        Return an NebTaskDoc from endpoint and NEB calculation directories.

        This method populates the endpoint and image fields completely,
        permitting an analysis of the barrier.
        """

        ep_dirs = [Path(ep_dir).resolve() for ep_dir in endpoint_directories]
        neb_dir = Path(neb_directory).resolve()

        endpoint_calculations: list[Calculation | None] = [None, None]
        endpoint_objects = [None, None]
        for idx, endpoint_dir in enumerate(ep_dirs):
            vasp_files = _find_vasp_files(
                endpoint_dir, volumetric_files=volumetric_files
            )

            if vasp_files.get("standard"):
                ep_key = "standard"
            else:
                max_rel_idx = max(
                    int(k.split("relax")[-1])
                    for k in vasp_files
                    if k.startswith("relax")
                )
                ep_key = f"relax{max_rel_idx}"

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

        img_dirs = sorted(neb_dir.glob("[0-9][0-9]"))
        ep_img_dirs = [img_dirs[0], img_dirs[-1]]
        endpoint_energies: list[float | None] = [None, None]
        endpoint_structures: list[Structure | None] = [None, None]
        for idx, ep_calc in enumerate(endpoint_calculations):
            if ep_calc is None:
                ep_dirs[idx] = ep_img_dirs[idx]
                endpoint_structures[idx] = Structure.from_file(
                    zpath(f"{ep_dirs[idx]}/POSCAR")
                )
            else:
                endpoint_structures[idx] = ep_calc.output.structure
                endpoint_energies[idx] = ep_calc.output.energy

        intermediate_images = NebIntermediateImagesDoc.from_directory(
            neb_dir,
            volumetric_files=volumetric_files,
            store_calculations=store_calculations,
            **kwargs,
        )

        states = [
            getattr(ep_calc, "state", TaskState.FAILED)
            for ep_calc in endpoint_calculations
        ] + [intermediate_images.state]

        state = TaskState.SUCCESS
        if any(calc_state == TaskState.FAILED for calc_state in states):
            state = TaskState.FAILED
        elif any(calc_state == TaskState.ERROR for calc_state in states):
            state = TaskState.ERROR

        images = _join_endpoint_and_image_data(
            endpoint_structures, intermediate_images.images
        )
        calculations = None
        if store_calculations:
            calculations = _join_endpoint_and_image_data(
                endpoint_calculations, intermediate_images.calculations
            )

        return cls(
            images=images,
            initial_images=_join_endpoint_and_image_data(
                endpoint_structures, intermediate_images.initial_images
            ),
            image_indices=list(range(len(images))),
            energies=_join_endpoint_and_image_data(
                endpoint_energies, intermediate_images.energies
            ),
            state=state,
            neb_method=intermediate_images.neb_method,
            dir_name=str(intermediate_images.dir_name),
            directories=_join_endpoint_and_image_data(
                ep_dirs, intermediate_images.directories, map_fun=str
            ),
            calculations=calculations,
            objects=_join_endpoint_and_image_data(
                endpoint_objects, intermediate_images.objects
            ),
            **kwargs,
        )


@arrow_incompatible
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

    host_structure: StructureType | None = Field(
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
