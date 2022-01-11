""" Core definition of a Q-Chem Task Document """
from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field
from pymatgen.core.structure import Molecule

from emmet.core.math import Matrix3D, Vector3D
from emmet.core.structure import MoleculeMetadata
from emmet.core.task import TaskDocument as BaseTaskDocument
from emmet.core.utils import ValueEnum
from emmet.core.qchem.calc_types import (
    LevelOfTheory,
    CalcType,
    TaskType,
    calc_type,
    level_of_theory,
    task_type
)


class Status(ValueEnum):
    """
    Q-Chem Calculation State
    """

    SUCESS = "successful"
    FAILED = "unsuccessful"


class OutputSummary(BaseModel):
    """
    Summary of an output for a Q-Chem calculation
    """

    initial_molecule: Molecule = Field(None, description="Input Molecule object")
    optimized_molecule: Molecule = Field(None, description="Optimized Molecule object")

    final_energy: float = Field(None, description="Final electronic energy for the calculation (units: Hartree)")
    enthalpy: float = Field(None, description="Total enthalpy of the molecule (units: kcal/mol)")
    entropy: float = Field(None, description="Total entropy of the molecule (units: cal/mol-K")

    mulliken: List[Any] = Field(None,
                                description="Mulliken atomic partial charges and partial spins")
    resp: List[float] = Field(None,
                            description="Restrained Electrostatic Potential (RESP) atomic partial charges")
    nbo: Dict[str, Any] = Field(None,
                                description="Natural Bonding Orbital (NBO) output")

    frequencies: List[float] = Field(None,
                                     description="Vibrational frequencies of the molecule (units: cm^-1)")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "initial_molecule": self.initial_molecule,
            "optimized_molecule": self.optimized_molecule,
            "final_energy": self.final_energy,
            "enthalpy": self.enthalpy,
            "entropy": self.entropy,
            "mulliken": self.mulliken,
            "resp": self.resp,
            "nbo": self.nbo,
            "frequencies": self.frequencies,
        }


class TaskDocument(BaseTaskDocument, MoleculeMetadata):
    """
    Definition of a Q-Chem task document
    """

    calc_code = "Q-Chem"
    completed = True

    is_valid: bool = Field(
        True, description="Whether this task document passed validation or not"
    )
    state: Status = Field(None, description="State of this calculation")

    cputime: float = Field(None, description="The system CPU time in seconds")
    walltime: float = Field(None, description="The real elapsed time in seconds")

    calcs_reversed: List[Dict] = Field(
        [], description="The 'raw' calculation docs used to assembled this task"
    )

    orig: Dict[str, Any] = Field(
        {}, description="Summary of the original Q-Chem inputs"
    )
    output = Field(OutputSummary())

    critic2: Dict[str, Any] = Field(None,
                                    description="Output from Critic2 critical point analysis code")
    custom_smd: str = Field(None,
                            description="Parameter string for SMD implicit solvent model")

    special_run_type: str = Field(None,
                                  description="Special workflow name (if applicable)")

    tags: Dict[str, Any] = Field(None,
                                 description="Metadata tags")

    warnings: Dict[str, bool] = Field(
        None, description="Any warnings related to this task document"
    )

    @property
    def level_of_theory(self) -> LevelOfTheory:
        return level_of_theory(self.orig, custom_smd=self.custom_smd)

    @property
    def task_type(self) -> TaskType:
        return task_type(self.orig, special_run_type=self.special_run_type)

    @property
    def calc_type(self) -> CalcType:
        return calc_type(
            self.special_run_type,
            self.orig,
            custom_smd=self.custom_smd
        )

    @property
    def entry(self) -> Dict[str, Any]:

        if self.output.optimized_molecule is not None:
            mol = self.output.optimized_molecule
        else:
            mol = self.output.initial_molecule

        entry_dict = {
            "entry_id": self.task_id,
            "charge": self.charge,
            "spin_multiplicity": self.spin_multiplicity,
            "level_of_theory": self.level_of_theory,
            "task_type": self.task_type,
            "calc_type": self.calc_type,
            "molecule": mol,
            "composition": mol.composition,
            "formula": mol.composition.alphabetical_formula,
            "energy": self.output.final_energy,
            "output": self.output.as_dict(),
            "orig": self.orig,
            "tags": self.tags,
            "last_updated": self.last_updated
        }

        return entry_dict