"""Schemas for OpenMM tasks."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from emmet.core.openff import MDTaskDocument  # type: ignore[import-untyped]
from emmet.core.openff.tasks import CompressedStr  # type: ignore[import-untyped]
from emmet.core.vasp.task_valid import TaskState

if TYPE_CHECKING:
    from typing import Any

from emmet.core.utils import arrow_incompatible, type_override


@arrow_incompatible
class CalculationInput(BaseModel):  # type: ignore[call-arg]
    """OpenMM input settings for a job, these are the attributes of the OpenMMMaker."""

    n_steps: int | None = Field(
        None, description="The number of simulation steps to run."
    )

    step_size: float | None = Field(
        None, description="The size of each simulation step (picoseconds)."
    )

    temperature: float | None = Field(
        None, description="The simulation temperature (kelvin)."
    )

    pressure: float | None = Field(
        None, description="The simulation pressure (atmospheres)."
    )

    friction_coefficient: float | None = Field(
        None,
        description=(
            "The friction coefficient for the integrator (inverse picoseconds)."
        ),
    )

    platform_name: str | None = Field(
        None,
        description=(
            "The name of the OpenMM platform to use, passed to "
            "Interchange.to_openmm_simulation."
        ),
    )

    platform_properties: dict | None = Field(
        None,
        description=(
            "Properties for the OpenMM platform, passed to "
            "Interchange.to_openmm_simulation."
        ),
    )

    state_interval: int | None = Field(
        None,
        description=(
            "State is saved every `state_interval` timesteps. For no state, set to 0."
        ),
    )

    state_file_name: str | None = Field(
        None, description="The name of the state file to save."
    )

    traj_interval: int | None = Field(
        None,
        description=(
            "The trajectory is saved every `traj_interval` timesteps. For no trajectory, set to 0."
        ),
    )

    wrap_traj: bool | None = Field(
        None, description="Whether to wrap trajectory coordinates."
    )

    report_velocities: bool | None = Field(
        None, description="Whether to report velocities in the trajectory file."
    )

    traj_file_name: str | None = Field(
        None, description="The name of the trajectory file to save."
    )

    traj_file_type: str | None = Field(
        None,
        description="The type of trajectory file to save.",
    )

    embed_traj: bool | None = Field(
        None,
        description="Whether to embed the trajectory blob in CalculationOutput.",
    )

    model_config = ConfigDict(extra="allow")


@type_override({"traj_blob": str})
class CalculationOutput(BaseModel):
    """OpenMM calculation output files and extracted data."""

    dir_name: str | None = Field(None, description="The directory for this OpenMM task")

    traj_file: str | None = Field(
        None, description="Path to the trajectory file relative to `dir_name`"
    )

    traj_blob: CompressedStr | None = Field(
        None, description="Trajectory file bytes blob hex encoded to a string"
    )

    state_file: str | None = Field(
        None, description="Path to the state file relative to `dir_name`"
    )

    steps_reported: list[int] | None = Field(
        None, description="Steps where outputs are reported"
    )

    time: list[float] | None = Field(None, description="List of times")

    potential_energy: list[float] | None = Field(
        None, description="List of potential energies"
    )

    kinetic_energy: list[float] | None = Field(
        None, description="List of kinetic energies"
    )

    total_energy: list[float] | None = Field(None, description="List of total energies")

    temperature: list[float] | None = Field(None, description="List of temperatures")

    volume: list[float] | None = Field(None, description="List of volumes")

    density: list[float] | None = Field(None, description="List of densities")

    elapsed_time: float | None = Field(
        None, description="Elapsed time for the calculation (seconds)."
    )

    @classmethod
    def from_directory(
        cls,
        dir_name: Path | str,
        state_file_name: str,
        traj_file_name: str,
        elapsed_time: float | None = None,
        embed_traj: bool = False,
    ) -> CalculationOutput:
        """Extract data from the output files in the directory."""
        state_file = Path(dir_name) / state_file_name
        column_name_map: dict[str, str] = {
            '#"Step"': "steps_reported",
            "Potential Energy (kJ/mole)": "potential_energy",
            "Kinetic Energy (kJ/mole)": "kinetic_energy",
            "Total Energy (kJ/mole)": "total_energy",
            "Temperature (K)": "temperature",
            "Box Volume (nm^3)": "volume",
            "Density (g/mL)": "density",
        }
        state_is_not_empty = state_file.exists() and state_file.stat().st_size > 0
        if state_is_not_empty:
            data = pd.read_csv(state_file, header=0)
            data = data.rename(columns=column_name_map)
            data = data.filter(items=list(column_name_map.values()))
            attributes: dict[str, Any] = data.to_dict(orient="list")  # type: ignore[assignment]
        else:
            attributes = {name: None for name in column_name_map.values()}
            state_file_name = None  # type: ignore[assignment]

        traj_file = Path(dir_name) / traj_file_name
        traj_is_not_empty = traj_file.exists() and traj_file.stat().st_size > 0
        traj_file_name = traj_file_name if traj_is_not_empty else None  # type: ignore

        traj_blob: str | None = None
        if traj_is_not_empty and embed_traj:
            with open(traj_file, "rb") as f:
                traj_blob = f.read().hex()

        return CalculationOutput(
            dir_name=str(dir_name),
            elapsed_time=elapsed_time,
            traj_file=traj_file_name,
            state_file=state_file_name,
            traj_blob=traj_blob,
            **attributes,
        )


@arrow_incompatible
class Calculation(BaseModel):
    """All input and output data for an OpenMM calculation."""

    dir_name: str | None = Field(
        None, description="The directory for this OpenMM calculation"
    )

    has_openmm_completed: TaskState | bool | None = Field(
        None, description="Whether OpenMM completed the calculation successfully"
    )

    input: CalculationInput | None = Field(
        None, description="OpenMM input settings for the calculation"
    )
    output: CalculationOutput | None = Field(
        None, description="The OpenMM calculation output"
    )

    completed_at: str | None = Field(
        None, description="Timestamp for when the calculation was completed"
    )
    task_name: str | None = Field(
        None, description="Name of task given by custodian (e.g., relax1, relax2)"
    )

    calc_type: str | None = Field(
        None,
        description="Return calculation type (run type + task_type). or just new thing",
    )


class OpenMMTaskDocument(MDTaskDocument):
    """Definition of the OpenMM task document."""

    calcs_reversed: list[Calculation] | None = Field(
        None,
        title="Calcs reversed data",
        description="Detailed data for each OpenMM calculation contributing to the "
        "task document.",
    )
