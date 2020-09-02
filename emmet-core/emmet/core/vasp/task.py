""" Core definition of a VASP Task Document """
from datetime import datetime
from enum import Enum
from functools import partial
from typing import ClassVar, Dict, List, Optional, Union

from pydantic import BaseModel, Field, create_model
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer, Ordering

from emmet.core.structure import StructureMetadata
from emmet.stubs import Matrix3D, Structure


class Status(Enum):
    """
    VASP Calculation State
    """

    SUCESS = "sucess"
    FAILED = "failed"


class InputSummary(BaseModel):
    """
    Summary of inputs for a VASP calculation
    """

    structure: Structure = Field(..., description="The input structure object")
    parameters: Dict = Field(
        ...,
        description="Input parameters from VASPRUN for the last calculation in the series",
    )
    pseudo_potentials: Dict = Field(
        ..., description="Summary of the pseudopotentials used in this calculation"
    )


class OutputSummary(BaseModel):
    """
    Summary of the outputs for a VASP calculation
    """

    structure: Structure = Field(..., description="The output structure object")
    energy: float = Field(
        ..., description="The final total DFT energy for the last calculation"
    )
    energy_per_atom: float = Field(
        ..., description="The final DFT energy per atom for the last calculation"
    )
    bandgap: float = Field(..., description="The DFT bandgap for the last calculation")
    forces: List[Matrix3D] = Field(
        ..., description="Forces on atoms from the last calculation"
    )
    stress: Matrix3D = Field(
        ..., description="Stress on the unitcell from the last calculation"
    )


class RunStatistics(BaseModel):
    """
    Summary of the Run statistics for a VASP calculation
    """

    average_memory: float = Field(..., description="The average memory used in kb")
    max_memory: float = Field(..., description="The maximum memory used in kb")
    elapsed_time: float = Field(..., description="The real time elapsed in seconds")
    system_time: float = Field(..., description="The system CPU time in seconds")
    user_time: float = Field(
        ..., description="The user CPU time spent by VASP in seconds"
    )
    total_time: float = Field(
        ..., description="The total CPU time for this calculation"
    )
    cores: int = Field(..., description="The number of cores used by VASP")


class TaskDocument(StructureMetadata):
    """
    Definition of VASP Task Document
    """

    dir_name: str = Field(..., description="The directory for this VASP task")
    run_stats: Dict[str, RunStatistics] = Field(
        ...,
        description="Summary of runtime statisitics for each calcualtion in this task",
    )
    completed_at: datetime = Field(
        ..., description="Timestamp for when this task was completed"
    )
    last_updated: datetime = Field(
        ..., description="Timestamp for this task document was last updateed"
    )

    input: InputSummary
    output: OutputSummary

    state: State

    orig_inputs: Dict[str, Dict] = Field(
        ..., description="Summary of the original VASP inputs"
    )
    task_id: str = Field(None, description="the Task ID For this document")
    tags: List[str] = Field(None, description="Metadata tags for this task document")
