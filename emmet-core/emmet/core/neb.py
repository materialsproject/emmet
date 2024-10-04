"""Schemas and utils for NEB calculations."""

from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional, Tuple, Union
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

    endpoint_structures: tuple[Structure, Structure] = Field(
        None,
        description="The initial and final configurations (reactants and products) of the barrier.",
    )

    image_calculations: Optional[list[Calculation]] = Field(
        None, description="Full calculation output for the NEB images."
    )
    image_energies: Optional[list[float]] = Field(
        None, description="Final energies for each image"
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

    @classmethod
    def from_directory(
        cls,
        dir_name: Union[Path, str],
        volumetric_files: Tuple[str, ...] = _VOLUMETRIC_FILES,
        **neb_task_doc_kwargs,
    ) -> Self:
        if isinstance(dir_name, str):
            dir_name = Path(dir_name)

        neb_directories = sorted(dir_name.glob("[0-9][0-9]"))

        endpoint_directories = [neb_directories[0], neb_directories[-1]]
        endpoint_structures = [
            Structure.from_file(zpath(f"{endpoint_dir}/POSCAR"))
            for endpoint_dir in endpoint_directories
        ]

        image_directories = neb_directories[1:-1]

        image_calculations = []
        image_objects = {}
        for iimage, image_dir in enumerate(image_directories):
            vasp_files = _find_vasp_files(image_dir, volumetric_files=volumetric_files)

            calc, image_objects[iimage] = Calculation.from_vasp_files(
                dir_name=image_dir,
                task_name=f"NEB image {iimage + 1}",
                vasprun_file=vasp_files["standard"]["vasprun_file"],
                outcar_file=vasp_files["standard"]["outcar_file"],
                contcar_file=vasp_files["standard"]["contcar_file"],
                volumetric_files=vasp_files["standard"]["volumetric_files"],
                oszicar_file=vasp_files["standard"]["oszicar_file"],
                vasprun_kwargs={
                    "parse_potcar_file": False,
                },
            )
            image_calculations.append(calc)

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

        return cls(
            endpoint_structures=endpoint_structures,
            image_calculations=image_calculations,
            dir_name=str(dir_name),
            image_directories=[str(img_dir) for img_dir in image_directories],
            orig_inputs=inputs["orig_inputs"],
            inputs=inputs["inputs"],
            image_objects=image_objects,
            neb_method=(
                NebMethod.CLIMBING_IMAGE
                if inputs["inputs"].incar.get("LCLIMB")
                else NebMethod.STANDARD
            ),
            state=task_state,
            image_energies=[calc.output.energy for calc in image_calculations],
            custodian=_parse_custodian(dir_name),
            completed_at=max(calc.completed_at for calc in image_calculations),
            **neb_task_doc_kwargs,
        )
