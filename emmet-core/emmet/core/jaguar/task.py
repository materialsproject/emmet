""" Core definition of a Q-Chem Task Document """
from typing import Any, Dict, List, Union, Optional, Callable

from datetime import datetime

from pydantic import BaseModel, Field
from pymatgen.core.structure import Molecule

from emmet.core.mpid import MPID
from emmet.core.math import Matrix3D, Vector3D
from emmet.core.structure import MoleculeMetadata
from emmet.core.vasp.task_valid import BaseTaskDocument
from emmet.core.utils import ValueEnum
from emmet.core.qchem.calc_types import (
    LevelOfTheory,
    CalcType,
    TaskType,
    calc_type,
    level_of_theory,
    task_type,
)


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class OutputSummary(BaseModel):
    """
    Summary of an output for a Jaguar calculation
    """

    molecule: Molecule = Field(None, description="Final Molecule object")

    atom_properties: List[Dict[str, Any]] = Field(
        None,
        description="Atomic properties, including partial charges and forces (units: various)")

    energy: float = Field(
        None, description="Final electronic energy for the calculation (units: Hartree)"
    )
    gas_phase_energy: float = Field(
        None, description="Gas-phase energy for the calculation (units: Hartree)"
    )
    one_electron_energy: float = Field(
        None, description="Energy contribution from one-electron integrals (units: Hartree)"
    )
    two_electron_energy: float = Field(
        None, description="Energy contribution from two-electron integrals (units: Hartree)"
    )
    a_posteriori_correction: float = Field(
        None, description="Energy correction made a posteriori (units: Hartree)"
    )
    nuclear_repulsion_energy: float = Field(
        None, description="Nuclear repulsion energy (units: Hartee)"
    )
    zero_point_energy: float = Field(
        None, description="Zero-point vibrational energy (units: kcal/mol)"
    )

    homo_alpha: float = Field(
        None, description="Relative energy of the alpha-electron Highest Occupied Molecular Orbital (HOMO) (units: Hartree)"
    )
    homo_beta: float = Field(
        None, description="Relative energy of the beta-electron Highest Occupied Molecular Orbital (HOMO) (units: Hartree)"
    )
    lumo_alpha: float = Field(
        None, description="Relative energy of the alpha-electron Lowest Unoccupied Molecular Orbital (LUMO) (units: Hartree)"
    )
    lumo_beta: float = Field(
        None, description="Relative energy of the alpha-electron Lowest Unoccupied Molecular Orbital (LUMO) (units: Hartree)"
    )

    thermo: List[Dict[str, Any]] = Field(
        None, description="Thermodynamic information (energy, enthalpy, entropy, etc.) at various temperatures (units: various)"
    )

    frequencies: List[float] = Field(
        None, description="Vibrational frequencies of the molecule (units: cm^-1)"
    )
    vibrational_frequency_modes: List[List[List[float]]] = Field(
        None, description="Normal mode vectors of the molecule (units: Angstrom)"
    )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "@module": self.__class__.__module__,
            "@class": self.__class__.__name__,
            "molecule": self.molecule,
            "atom_properties": self.atom_properties,
            "energy": self.energy,
            "thermo": self.thermo,
            "frequencies": self.frequencies,
            "vibrational_frequency_modes": self.vibrational_frequency_modes
        }


class TaskDocument(BaseTaskDocument, MoleculeMetadata):
    """
    Definition of a Jaguar task document
    """

    calc_code: str = Field("Jaguar", description="The code used for thie calculation")
    version: str = Field(None, description="The version of the calculation code")
    path: str = Field(None, description="The directory for this calculation")
    calcid: MPID = Field(None, description="the calculation ID For this document")

    completed: bool = Field(False, description="Whether this calculation completed")

    last_updated: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp for this task document was last updated",
    )

    name: str = Field(
        None, description="Name of this calculation"
    )
    job_id: str = Field(
        None, description="Internal JobDB ID for this Jaguar calculation"
    )

    is_valid: bool = Field(
        True, description="Whether this task document passed validation or not"
    )
    success: bool = Field(None, description="Did this calculation succeed?")

    walltime: float = Field(None, description="The real elapsed time in seconds")

    input: Dict[str, Any] = Field(
        {}, description="Summary of the original Jaguar inputs"
    )
    output = Field(OutputSummary())


    tags: Dict[str, Any] = Field(None, description="Metadata tags")

    errors: Dict[str, Any] = Field(
        None, description="Any errors related to this calculation"
    )

    additional_data: Any = Field(
        None, description="Additional data about this calculation"
    )

    nelectrons: int = Field(
        None, description="Number of electrons in this calculation"
    )

    @property
    def level_of_theory(self) -> LevelOfTheory:
        return level_of_theory(self.orig, custom_smd=self.custom_smd)

    @property
    def task_type(self) -> TaskType:
        return task_type(self.orig, special_run_type=self.special_run_type)

    @property
    def calc_type(self) -> CalcType:
        return calc_type(self.special_run_type, self.orig, custom_smd=self.custom_smd)

    @property
    def entry(self) -> Dict[str, Any]:

        if self.output.optimized_molecule is not None:
            mol = self.output.optimized_molecule
        else:
            mol = self.output.initial_molecule

        if self.charge is None:
            charge = mol.charge
        else:
            charge = self.charge

        if self.spin_multiplicity is None:
            spin = mol.spin_multiplicity
        else:
            spin = self.spin_multiplicity

        entry_dict = {
            "entry_id": self.task_id,
            "task_id": self.task_id,
            "charge": charge,
            "spin_multiplicity": spin,
            "level_of_theory": self.level_of_theory,
            "custom_smd": self.custom_smd,
            "task_type": self.task_type,
            "calc_type": self.calc_type,
            "molecule": mol,
            "composition": mol.composition,
            "formula": mol.composition.alphabetical_formula,
            "energy": self.output.final_energy,
            "output": self.output.as_dict(),
            "critic2": self.critic2,
            "orig": self.orig,
            "tags": self.tags,
            "last_updated": self.last_updated,
        }

        return entry_dict


def filter_task_type(
    entries: List[Dict[str, Any]],
    task_type: TaskType,
    sort_by: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """
    Filter (and sort) TaskDocument entries based on task type

    :param entries: List of TaskDocument entry dicts
    :param TaskType: TaskType to accept
    :param sorted: Function used to sort (default None)
    :return: Filtered (sorted) list of entries
    """

    filtered = [f for f in entries if f["task_type"] == task_type]

    if sort_by is not None:
        return sorted(filtered, key=lambda x: x["output"]["final_energy"])
    else:
        return filtered
