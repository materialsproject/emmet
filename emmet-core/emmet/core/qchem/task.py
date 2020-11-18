""" Core definition of a Q-Chem Task Document """

from datetime import datetime
from typing import List, Dict

from pydantic import Field

from emmet.core.utils import ValueEnum
from emmet.core.qchem.mol_metadata import MoleculeMetadata
from emmet.core.qchem.mol_entry import MoleculeEntry
from emmet.core.qchem.input import InputSummary
from emmet.core.qchem.output import OutputSummary
from emmet.core.qchem.calc_types import task_type, TaskType, LevelOfTheory, calc_type


class Status(ValueEnum):
    """
    Q-Chem Calculation State
    """

    SUCESS = "successful"
    FAILED = "unsuccessful"


class TaskDocument(MoleculeMetadata):
    """
    Definition of Q-Chem Task Document
    """

    dir_name: str = Field(None, description="The directory for this Q-Chem task")

    created_at: datetime = Field(
        None, description="Timestamp for when this task was created"
    )

    completed_at: datetime = Field(
        None, description="Timestamp for when this task was completed"
    )

    last_updated: datetime = Field(
        None, description="Timestamp for this task document was last updated"
    )

    input: InputSummary = Field(None)
    output: OutputSummary = Field(None)

    metadata: Dict = Field(None, description="Calculation metadata")

    state: Status = Field(None, description="State of this calculation")

    orig: InputSummary = Field(
        None, description="Summary of the original Q-Chem inputs"
    )

    task_id: str = Field(None, description="the Task ID For this document")
    tags: List[str] = Field([], description="Metadata tags for this task document")

    @property
    def task_type(self):
        return task_type(self.input.parameters, self.metadata)

    @property
    def level_of_theory(self):
        return self.input.level_of_theory

    @property
    def lot_string(self):
        return self.input.level_of_theory.as_string

    @property
    def calc_type(self):
        return calc_type(self.input.parameters, self.metadata)

    @property
    def entry(self):
        """ Turns a Task Doc into a MoleculeEntry"""
        entry_dict = {
            "entry_id": self.task_id,
            "composition": self.output.molecule.composition,
            "energy": self.output.energy,
            "enthalpy": self.output.enthalpy,
            "entropy": self.output.entropy,
            "parameters": {
                "lot": self.input.level_of_theory.as_string,
                "other": self.input.parameters,
            },
            "data": {
                "last_updated": self.last_updated,
                "frequencies": self.output.frequencies,
                "vibrational_frequency_modes": self.output.vibrational_frequency_modes,
                "ir_active": self.output.modes_ir_active,
                "ir_intensity": self.output.modes_ir_intensity,
                "mulliken_charges": self.output.mulliken_charges,
                "mulliken_spin": self.output.mulliken_spin,
                "resp_charges": self.output.resp_charges,
                "bonding": self.output.bonding.bonding,
            },
        }

        return MoleculeEntry(**entry_dict)
