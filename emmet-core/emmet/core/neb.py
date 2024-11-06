"""Schemas and utils for NEB calculations."""

from datetime import datetime
import numpy as np
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from scipy.interpolate import CubicSpline
from typing import Optional, Tuple, Union, Sequence, Any
from typing_extensions import Self

from monty.os.path import zpath
from pymatgen.core import Structure

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
from emmet.core.vasp.calculation import Calculation
from emmet.core.vasp.task_valid import TaskState


class NebMethod(ValueEnum):
    """Common methods for NEB calculations.

    TODO: convert to StrEnum
    """

    STANDARD = "standard"
    CLIMBING_IMAGE = "climbing_image"
    APPROX = "approxNEB"


class NebTaskDoc(BaseModel, extra="allow"):
    """Define schema for VASP NEB tasks."""

    endpoint_structures: Sequence[Structure] = Field(
        None,
        description="The initial and final configurations (reactants and products) of the barrier.",
    )
    endpoint_energies : Optional[Sequence[float]] = Field(
        None,
        description="Energies of the endpoint structures."
    )
    endpoint_calculations : Optional[list[Calculation]] = Field(
        None,
        description = "Calculation information for the endpoint structures"
    )
    endpoint_objects : Optional[list[dict]] = Field(
        None, description="VASP objects for each endpoint calculation."
    )
    endpoint_directories : Optional[list[str]] = Field(
        None, description="List of the directories for the endpoint calculations."
    )

    image_structures: list[Structure] = Field(
        None, description="Final structures for each NEB images."
    )
    image_energies: Optional[list[float]] = Field(
        None, description="Final energies for each image"
    )
    image_calculations: Optional[list[Calculation]] = Field(
        None, description="Full calculation output for the NEB images."
    )
    dir_name: str = Field(None, description="Top-level NEB calculation directory.")

    image_directories: list[str] = Field(
        None, description="List of the directories where the NEB images are located"
    )
    image_objects: Optional[dict[int, dict]] = Field(
        None, description="VASP objects for each image calculation."
    )

    orig_inputs: Optional[OrigInputs] = Field(
        None,
        description="The exact set of input parameters used to generate the current task document.",
    )

    inputs: Optional[InputDoc] = Field(
        None, description="Inputs used in this calculation."
    )

    neb_method: Optional[NebMethod] = Field(
        None, description="The NEB method used for this calculation."
    )

    state: Optional[TaskState] = Field(None, description="State of this calculation")

    custodian: Optional[list[CustodianDoc]] = Field(
        None,
        description="Detailed custodian data for each VASP calculation contributing to the task document.",
    )

    last_updated: Optional[datetime] = Field(
        utcnow(),
        description="Timestamp for the most recent calculation for this task document",
    )

    completed_at: Optional[datetime] = Field(
        None, description="Timestamp for when this task was completed"
    )

    forward_barrier: Optional[float] = Field(
        None,
        description=(
            "Forward barrier for this reaction, "
            "i.e., the transition state energy minus "
            "the reactant / initial configuration energy."
        ),
    )

    reverse_barrier: Optional[float] = Field(
        None,
        description=(
            "Reverse barrier for this reaction, "
            "i.e., the transition state energy minus "
            "the product / final configuration energy."
        ),
    )

    barrier_analysis: Optional[dict[str, Any]] = Field(
        None, description="Analysis of the reaction barrier."
    )

    @model_validator(mode="after")
    def set_barriers(self) -> Self:
        """Perform analysis on barrier if needed."""
        if not self.forward_barrier or not self.reverse_barrier:
            self.barrier_analysis = neb_barrier_spline_fit(self.energies)
            for k in ("forward", "reverse"):
                setattr(self, f"{k}_barrier", self.barrier_analysis[f"{k}_barrier"])
        return self

    @property
    def num_images(self) -> int:
        """Return the number of VASP calculations / number of images performed."""
        return len(self.image_directories)
    
    @property
    def energies(self) -> list[float]:
        """Return the endpoint (optional) and image energies."""
        if self.endpoint_energies is not None:
            return [self.endpoint_energies[0], *self.image_energies, self.endpoint_energies[1]]
        return self.image_energies

    @property
    def structures(self) -> list[Structure]:
        """Return the endpoint and image structures."""
        return [self.endpoint_structures[0], *self.image_structures, self.endpoint_structures[1]]
   
    @classmethod
    def from_directory(
        cls,
        dir_name: Union[Path, str],
        volumetric_files: Tuple[str, ...] = _VOLUMETRIC_FILES,
        store_calculations : bool = True,
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

        if (ep_calcs := neb_task_doc_kwargs.pop("endpoint_calculations", None) ) is None:
            endpoint_directories = [neb_directories[0], neb_directories[-1]]
            endpoint_structures = [
                Structure.from_file(zpath(f"{endpoint_dir}/POSCAR"))
                for endpoint_dir in endpoint_directories
            ]
            endpoint_energies = None
        else:
            endpoint_directories = neb_task_doc_kwargs.pop("endpoint_directories")
            endpoint_structures = [
                ep_calc.output.structure for ep_calc in ep_calcs
            ]
            endpoint_energies = [
                ep_calc.output.energy for ep_calc in ep_calcs
            ]

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
                calc.has_vasp_completed == TaskState.SUCCESS
                for calc in calcs_to_check
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
            endpoint_energies = endpoint_energies,
            endpoint_directories = [str(ep_dir) for ep_dir in endpoint_directories],
            endpoint_calculations = ep_calcs if store_calculations else None,
            image_calculations=image_calculations if store_calculations else None,
            image_structures = image_structures,
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
        volumetric_files: Tuple[str, ...] = _VOLUMETRIC_FILES,
        **neb_task_doc_kwargs
    ) -> Self:
        """
        Return an NebTaskDoc from endpoint and NEB calculation directories.

        This method populates the endpoint and image fields completely,
        permitting an analysis of the barrier.
        """
        endpoint_calculations = [None for _ in range(2)]
        endpoint_objects = [None for _ in range(2)]
        for idx, endpoint_dir in enumerate(endpoint_directories):
            vasp_files = _find_vasp_files(endpoint_dir, volumetric_files=volumetric_files)
            ep_key = "standard" if vasp_files.get("standard") else "relax" + str(max(
                int(k.split("relax")[-1]) for k in vasp_files if k.startswith("relax")
            ))

            endpoint_calculations[idx], endpoint_objects[idx] = Calculation.from_vasp_files(
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
            endpoint_calculations = endpoint_calculations,
            endpoint_objects = endpoint_objects,
            endpoint_directories = endpoint_directories,
            **neb_task_doc_kwargs
        )
    
def neb_barrier_spline_fit(
    energies: Sequence[float],
    spline_kwargs: dict | None = None,
    frame_match_tol: float = 1.0e-6,
) -> dict[str, Any]:
    """
    Define basic NEB analysis tools.

    Parameters
    ----------
    energies : Sequence[float]
        The energies sorted by increasing frame index. Must include endpoints.
    frame_match_tol : float = 1.e-6
        The tolerance for matching the transition state frame index to the
        input frame indices.
    """
    analysis: dict[str, Any] = {
        "energies": list(energies),
        "frame_index": list(frame_idx := np.linspace(0.0, 1.0, len(energies))),
    }
    energies = np.array(energies)

    spline_kwargs = spline_kwargs or {"bc_type": "clamped"}
    spline_fit = CubicSpline(frame_idx, energies, **spline_kwargs)
    analysis["cubic_spline_pars"] = list(spline_fit.c)

    crit_points = spline_fit.derivative().roots()
    analysis["ts_frame_index"] = -1
    analysis["ts_energy"] = -np.inf
    for crit_point in crit_points:
        if (energy := spline_fit(crit_point)) > analysis["ts_energy"] and spline_fit(
            crit_point, 2
        ) <= 0.0:
            analysis["ts_frame_index"] = crit_point
            analysis["ts_energy"] = float(energy)

    analysis["ts_in_frames"] = any(
        abs(analysis["ts_frame_index"] - frame_idx)
        < frame_match_tol * max(frame_idx, frame_match_tol)
        for frame_idx in frame_idx
    )
    analysis["forward_barrier"] = analysis["ts_energy"] - energies[0]
    analysis["reverse_barrier"] = analysis["ts_energy"] - energies[-1]

    return analysis
