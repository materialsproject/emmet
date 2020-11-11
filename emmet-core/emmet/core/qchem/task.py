""" Core definition of a Q-Chem Task Document """

from datetime import datetime
from typing import Dict, List, Union, Tuple

from pydantic import BaseModel, Field, validator

from emmet.core import SETTINGS
from emmet.stubs import Matrix3D, Vector3D, Molecule
from emmet.core.utils import ValueEnum
from emmet.qchem.molecule import MoleculeMetadata, MoleculeEntry


class Status(ValueEnum):
    """
    Q-Chem Calculation State
    """

    SUCESS = "successful"
    FAILED = "failed"


class InputSummary(BaseModel):
    """
    Summary of inputs for a Q-Chem calculation
    """

    molecule: Molecule = Field(
        None, description="The input Molecule for this calculation"
    )

    functional: str = Field(
        None, description="Density functional used for this calculation"
    )

    basis: str = Field(None, description="Basis set used for this calculation")

    solvent_parameters: Dict = Field(
        None, description="Solvent model used for this calculations"
    )

    parameters: Dict = Field(
        None, description="Q-Chem input parameters for this calculation"
    )


class OutputSummary(BaseModel):
    """
    Summary of the outputs for a Q-Chem calculation
    """

    molecule: Molecule = Field(None, description="The output molecular structure")

    energy: float = Field(
        None, description="Final DFT energy for this calculation in eV"
    )

    enthalpy: float = Field(
        None, description="DFT-calculated total enthalpy correction in eV"
    )

    entropy: float = Field(None, description="DFT-calculated total entropy in eV/K")

    frequencies: List[float] = Field(
        None, description="Vibrational frequencies for this molecule"
    )

    vibrational_frequency_modes: List[List[Tuple[float, float, float]]] = Field(
        None, description="Frequency mode vectors for this molecule"
    )

    modes_ir_active: List[bool] = Field(
        None,
        description="Determination of if each mode should be considered in IR spectra",
    )

    modes_ir_intensity: List[float] = Field(
        None, description="IR intensity of vibrational frequency modes"
    )

    mulliken: Union[List[float], List[Tuple[float, float]]] = Field(
        None,
        description="Molecule partial charges and occupancies for each atom, as determined by Mulliken population analysis",
    )

    resp: List[float] = Field(
        None,
        description="Molecule partial charges, as determined by the Restrained Electrostatic Potential (RESP) method",
    )

    critic_bonding: List[Tuple[int, int]] = Field(
        None,
        description="Bonding information, obtained by Critic2 analysis of electron density critical points",
    )

    walltime: float = Field(None, description="The real time elapsed in seconds")

    cputime: float = Field(None, description="The system CPU time in seconds")


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

    is_valid: bool = Field(
        True, description="Whether this task document passed validation or not"
    )

    input: InputSummary = Field(None)
    output: OutputSummary = Field(None)

    state: Status = Field(None, description="State of this calculation")

    orig_input: InputSummary = Field(
        None, description="Summary of the original Q-Chem inputs"
    )

    task_id: str = Field(None, description="the Task ID For this document")
    tags: List[str] = Field([], description="Metadata tags for this task document")

    sandboxes: List[str] = Field(
        None, description="List of sandboxes this task document is allowed in"
    )

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

    # TODO: Figure out what this does and how/if I need to change it
    @validator("sandboxes", always=True)
    def tags_to_sandboxes(cls, v, values):
        tag_mapping = SETTINGS.TAGS_TO_SANDBOXES

        if v is None:
            if tag_mapping is not None:
                sandboxed_tags = {
                    tag for tag_list in tag_mapping.values() for tag in tag_list
                }

                if any(tag in sandboxed_tags for tag in values.get("tags", [])):
                    v = sorted(
                        {
                            sandbox
                            for sandbox, tags in tag_mapping.items()
                            if len(set(tags).intersection(values.get("tags", []))) > 0
                        }
                    )
                else:
                    v = ["core"]
            else:
                v = ["core"]
        return v
