""" Core definition of a CP2K Task Document """
from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, Field, validator
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.core import Structure
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

from emmet.core.task import TaskDocument as BaseTaskDocument
from emmet.core.structure import StructureMetadata
from emmet.core.utils import ValueEnum
from emmet.core.cp2k.calc_types import (
    CalcType,
    RunType,
    TaskType,
    calc_type,
    run_type,
    task_type,
)
from emmet.core.math import Matrix3D, Vector3D


class Status(ValueEnum):
    """
    CP2K Calculation State
    """

    SUCESS = "successful"
    FAILED = "failed"


class InputSummary(BaseModel):
    """
    Summary of inputs for a CP2K calculation
    """

    structure: Structure = Field(None, description="The input structure object")

    atomic_kind_info: Dict = Field(None, description="Description of parameters used for each atomic kind")

    cp2k_input_set: Dict = Field(None, description="The cp2k input used for this task")

    dft: Dict = Field(None, description="Description of the DFT parameters used in the last calc of this task")

    cp2k_global: Dict = Field(None, description="CP2K global parameters used in the last calc of this task")

    @validator('atomic_kind_info')
    def remove_unnecessary(cls, atomic_kind_info):
        for k in atomic_kind_info:
            if 'total_pseudopotential_energy' in atomic_kind_info[k]:
                del atomic_kind_info[k]['total_pseudopotential_energy']
        return atomic_kind_info

    @validator('dft')
    def cleanup_dft(cls, dft):
        if any(v.upper() == 'UKS' for v in dft.values()):
            dft['UKS'] = True
        return dft


class OutputSummary(BaseModel):
    """
    Summary of the outputs for a CP2K calculation
    """

    structure: Structure = Field(None, description="The output structure object")
    energy: float = Field(
        None, description="The final total DFT energy for the last calculation"
    )
    energy_per_atom: float = Field(
        None, description="The final DFT energy per atom for the last calculation"
    )
    bandgap: float = Field(None, description="The DFT band gap for the last calculation")
    forces: List[Vector3D] = Field(
        None, description="Forces on atoms from the last calculation"
    )
    stress: Matrix3D = Field(
        None, description="Stress on the unit cell from the last calculation"
    )


class RunStatistics(BaseModel):
    """
    Summary of the Run statistics for a CP2K calculation
    """

    average_memory: float = Field(None, description="The average memory used in kb")
    max_memory: float = Field(None, description="The maximum memory used in kb")
    elapsed_time: float = Field(None, description="The real time elapsed in seconds")
    system_time: float = Field(None, description="The system CPU time in seconds")
    user_time: float = Field(
        None, description="The user CPU time spent by CP2K in seconds"
    )
    total_time: float = Field(
        None, description="The total CPU time for this calculation"
    )
    cores: int = Field(None, description="The number of cores used by CP2K")


class TaskDocument(BaseTaskDocument, StructureMetadata):
    """
    Definition of CP2K Task Document
    """

    dir_name: str = Field(None, description="The directory for this CP2K task")
    run_stats: RunStatistics = Field(
        None,
        description="Summary of runtime statistics for each calculation in this task",
    )
    completed_at: datetime = Field(
        None, description="Timestamp for when this task was completed"
    )
    last_updated: datetime = Field(
        None, description="Timestamp for this task document was last updated"
    )

    is_valid: bool = Field(
        True, description="Whether this task document passed validation or not"
    )

    input: InputSummary = Field(None)

    output: OutputSummary = Field(None)

    state: Status = Field(None, description="State of this calculation")

    orig_inputs: Dict = Field(
        None, description="Summary of the original CP2K inputs"
    )
    task_id: int = Field(None, description="the Task ID For this document")
    tags: List[str] = Field([], description="Metadata tags for this task document")

    run_type: RunType = Field(None)
    task_type: TaskType = Field(None)
    calc_type: CalcType = Field(None)

    @validator('input', pre=True, always=True)
    def rename_global(cls, input):
        if 'cp2k_global' not in input:
            input['cp2k_global'] = input.pop('global')
        return input

    @validator('run_type', pre=True, always=True)
    def find_run_type(cls, v, values):
        return run_type(values.get('input').dft)

    @validator('task_type', pre=True, always=True)
    def find_task_type(cls, v, values):
        return task_type(values.get('input').cp2k_global)

    @validator('calc_type', pre=True, always=True)
    def find_calc_type(cls, v, values):
        d = values.get('input').dft
        d.update(values.get('input').cp2k_global)
        return calc_type(d)

    @property
    def entry(self):
        """ Turns a Task Doc into a ComputedEntry"""
        entry_dict = {
            "correction": 0.0,
            "entry_id": self.task_id,
            "composition": self.output.structure.composition,
            "energy": self.output.energy,
            "parameters": {
                "atomic_kind_info": self.input.atomic_kind_info,
                # This is done to be compatible with MontyEncoder for the ComputedEntry
                "run_type": str(self.run_type),
            },
            "data": {
                "oxide_type": oxide_type(self.output.structure),
                "last_updated": self.last_updated,
            },
        }

        return ComputedEntry.from_dict(entry_dict)

    @property
    def structure_entry(self) -> ComputedStructureEntry:
        """Turns a Task Doc into a ComputedStructureEntry"""
        entry_dict = {
            "correction": 0.0,
            "entry_id": self.task_id,
            "composition": self.output.structure.composition,
            "energy": self.output.energy,
            "parameters": {
                "atomic_kind_info": self.input.atomic_kind_info,
                # This is done to be compatible with MontyEncoder for the ComputedEntry
                "run_type": str(self.run_type),
            },
            "data": {
                "oxide_type": oxide_type(self.output.structure),
                "last_updated": self.last_updated,
            },
            "structure": self.output.structure,
        }

        return ComputedStructureEntry.from_dict(entry_dict)

