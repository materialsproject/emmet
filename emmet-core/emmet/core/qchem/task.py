""" Core definition of a Q-Chem Task Document """

from datetime import datetime
from typing import List

from pydantic import Field, validator

from emmet.core import SETTINGS
from emmet.core.utils import ValueEnum
from emmet.core.qchem.mol_metadata import MoleculeMetadata
from emmet.core.qchem.mol_entry import MoleculeEntry
from emmet.core.qchem.input import InputSummary
from emmet.core.qchem.output import OutputSummary


class Status(ValueEnum):
    """
    Q-Chem Calculation State
    """

    SUCESS = "successful"
    FAILED = "failed"


class TaskDocument(MoleculeMetadata):
    """
    Definition of Q-Chem Task Document
    """

    dir_name: str = Field(None, description="The directory for this Q-Chem task")

    completed_at: datetime = Field(
        None, description="Timestamp for when this task was completed"
    )

    last_updated: datetime = Field(
        None, description="Timestamp for this task document was last updated"
    )

    input: InputSummary = Field(None)
    output: OutputSummary = Field(None)

    state: Status = Field(None, description="State of this calculation")

    orig_input: InputSummary = Field(
        None, description="Summary of the original Q-Chem inputs"
    )

    task_id: str = Field(None, description="the Task ID For this document")
    tags: List[str] = Field([], description="Metadata tags for this task document")

    task_type: str = Field(None, description="Type of calculation performed")

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
                "functional": self.input.functional,
                "basis": self.input.basis,
                "solvent": self.input.solvent_parameters,
                "other": self.input.parameters,
            },
            "data": {
                "last_updated": self.last_updated,
                "frequencies": self.output.frequencies,
                "vibrational_frequency_modes": self.output.vibrational_frequency_modes,
                "ir_active": self.output.modes_ir_active,
                "ir_intensity": self.output.modes_ir_intensity,
            },
        }

        return MoleculeEntry(**entry_dict)
