""" Core definition of a Q-Chem Task Document """

from datetime import datetime
from typing import List, Dict, Type, TypeVar
import copy

from pydantic import Field

from emmet.core.utils import ValueEnum
from emmet.core.qchem.mol_metadata import MoleculeMetadata
from emmet.core.qchem.mol_entry import MoleculeEntry
from emmet.core.qchem.input import InputSummary
from emmet.core.qchem.output import OutputSummary
from emmet.core.qchem.calc_types import task_type, TaskType, LevelOfTheory, calc_type
from emmet.core.qchem.bonding import Bonding
from emmet.stubs import Molecule


class Status(ValueEnum):
    """
    Q-Chem Calculation State
    """

    SUCESSFUL = "successful"
    UNSUCCESSFUL = "unsuccessful"


S = TypeVar("S", bound="TaskDoc")


class TaskDoc(MoleculeMetadata):
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
        datetime.now(), description="Timestamp for this task document was last updated"
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

    @classmethod
    def from_dict(cls: Type[S], task_dict: Dict) -> S:
        d = dict()
        d["dir_name"] = task_dict.get("dir_name")

        if task_dict.get("state") == "successful":
            d["state"] = Status("successful")
        else:
            d["state"] = Status("unsuccessful")

        d["tags"] = task_dict.get("tags")
        d["task_id"] = task_dict.get("task_id")

        # Gather metadata
        metadata = dict()
        if "custom_smd" in task_dict:
            metadata["custom_smd"] = task_dict["custom_smd"]
        if "critic2" in task_dict:
            metadata["critic2"] = task_dict["critic2"]
        if "special_run_type" in task_dict:
            metadata["special_run_type"] = task_dict["special_run_type"]
        if "linked" in task_dict:
            metadata["linked"] = task_dict["linked"]

        # Input
        calcs_reversed = task_dict.get("calcs_reversed")
        if calcs_reversed is not None:
            final_input = calcs_reversed[-1].get("input")
            if final_input is None:
                d["input"] = None
            else:
                mol = Molecule.from_dict(final_input["molecule"])
                lot = LevelOfTheory.from_inputs(final_input, metadata)
                params = copy.deepcopy(final_input)
                del params["molecule"]
                d["input"] = InputSummary(molecule=mol,
                                          level_of_theory=lot,
                                          parameters=params)

        # Orig input
        orig = task_dict.get("orig")
        if orig is not None:
            mol = Molecule.from_dict(orig["molecule"])
            lot = LevelOfTheory.from_inputs(orig, metadata)
            params = copy.deepcopy(orig)
            del params["molecule"]
            d["orig"] = InputSummary(molecule=mol,
                                     level_of_theory=lot,
                                     parameters=params)

            if d["input"] is None:
                d["input"] = d["orig"]
        else:
            if d["input"] is not None:
                d["orig"] = d["input"]

        # Output
        output = dict()
        if "walltime" in task_dict:
            output["walltime"] = task_dict["walltime"]
        elif calcs_reversed is not None:
            total_wall = 0.0
            for calc in calcs_reversed:
                if "walltime" in calc:
                    total_wall += calc["walltime"]
            output["walltime"] = total_wall

        if "cputime" in task_dict:
            output["cputime"] = task_dict["cputime"]
        elif calcs_reversed is not None:
            total_cpu = 0.0
            for calc in calcs_reversed:
                if "cputime" in calc:
                    total_cpu += calc["cputime"]
            output["cputime"] = total_cpu

        out = task_dict.get("output")
        if out is not None:
            if task_dict.get("state") == "successful":
                if "optimized_molecule" in out:
                    output["molecule"] = Molecule.from_dict(out["optimized_molecule"])
                    # TODO: You are here
            else:
                output["molecule"] = Molecule.from_dict(out["initial_molecule"])
                output["bonding"] = Bonding.from_molecule(output["molecule"])
