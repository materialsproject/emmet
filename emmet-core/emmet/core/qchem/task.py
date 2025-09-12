"""Core definition of a Q-Chem Task Document"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from pymatgen.core.structure import Molecule

from emmet.core.mpid import MPID, MPculeID
from emmet.core.qchem.calc_types import (
    CalcType,
    LevelOfTheory,
    TaskType,
    calc_type,
    level_of_theory,
    lot_solvent_string,
    solvent,
    task_type,
)
from emmet.core.structure import MoleculeMetadata
from emmet.core.task import BaseTaskDocument
from emmet.core.types.enums import ValueEnum
from emmet.core.utils import arrow_incompatible

if TYPE_CHECKING:
    from collections.abc import Callable

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class QChemStatus(ValueEnum):
    """
    Q-Chem Calculation State
    """

    SUCCESS = "successful"
    FAILED = "unsuccessful"


@arrow_incompatible
class OutputSummary(BaseModel):
    """
    Summary of an output for a Q-Chem calculation
    """

    initial_molecule: Molecule | None = Field(None, description="Input Molecule object")
    optimized_molecule: Molecule | None = Field(
        None, description="Optimized Molecule object"
    )

    final_energy: float | None = Field(
        None, description="Final electronic energy for the calculation (units: Hartree)"
    )
    enthalpy: float | None = Field(
        None, description="Total enthalpy of the molecule (units: kcal/mol)"
    )
    entropy: float | None = Field(
        None, description="Total entropy of the molecule (units: cal/mol-K"
    )

    mulliken: list[Any] | None = Field(
        None, description="Mulliken atomic partial charges and partial spins"
    )
    resp: list[float] | None = Field(
        None,
        description="Restrained Electrostatic Potential (RESP) atomic partial charges",
    )
    nbo: dict[str, Any] | None = Field(
        None, description="Natural Bonding Orbital (NBO) output"
    )

    frequencies: list[float] | None = Field(
        None, description="Vibrational frequencies of the molecule (units: cm^-1)"
    )

    dipoles: dict[str, Any] | None = Field(
        None, description="Electric dipole information for the molecule"
    )

    gradients: list[list[float]] | None = Field(
        None, description="Atomic forces, in atomic units (Ha/Bohr)"
    )

    precise_gradients: list[list[float]] | None = Field(
        None, description="High-precision atomic forces, in atomic units (Ha/Bohr)"
    )

    pcm_gradients: list[list[float]] | None = Field(
        None,
        description="Electrostatic atomic forces from polarizable continuum model (PCM) implicit solvation,"
        "in atomic units (Ha/Bohr).",
    )

    CDS_gradients: list[list[float]] | None = Field(
        None,
        description="Atomic force contributions from cavitation, dispersion, and structural rearrangement in the SMx"
        "family of implicit solvent models, in atomic units (Ha/Bohr)",
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "@module": self.__class__.__module__,
            "@class": self.__class__.__name__,
            "initial_molecule": self.initial_molecule,
            "optimized_molecule": self.optimized_molecule,
            "final_energy": self.final_energy,
            "enthalpy": self.enthalpy,
            "entropy": self.entropy,
            "mulliken": self.mulliken,
            "resp": self.resp,
            "nbo": self.nbo,
            "frequencies": self.frequencies,
            "dipoles": self.dipoles,
            "gradients": self.gradients,
            "precise_gradients": self.precise_gradients,
        }


@arrow_incompatible
class TaskDocument(BaseTaskDocument, MoleculeMetadata):
    """
    Definition of a Q-Chem task document
    """

    task_id: MPID | MPculeID | None = Field(
        None, description="the Task ID For this document"
    )

    calc_code: str = "Q-Chem"
    completed: bool = True

    is_valid: bool = Field(
        True, description="Whether this task document passed validation or not"
    )
    state: QChemStatus | None = Field(None, description="State of this calculation")

    cputime: float | None = Field(None, description="The system CPU time in seconds")
    walltime: float | None = Field(None, description="The real elapsed time in seconds")

    calcs_reversed: list[dict] = Field(
        [], description="The 'raw' calculation docs used to assembled this task"
    )

    orig: dict[str, Any] = Field(
        {}, description="Summary of the original Q-Chem inputs"
    )
    output: OutputSummary = Field(OutputSummary())  # type: ignore[call-arg]

    critic2: dict[str, Any] | None = Field(
        None, description="Output from Critic2 critical point analysis code"
    )
    custom_smd: str | None = Field(
        None, description="Parameter string for SMD implicit solvent model"
    )

    special_run_type: str | None = Field(
        None, description="Special workflow name (if applicable)"
    )

    smiles: str | None = Field(
        None,
        description="Simplified molecular-input line-entry system (SMILES) string for the molecule involved "
        "in this calculation.",
    )

    species_hash: str | None = Field(
        None,
        description="Weisfeiler Lehman (WL) graph hash using the atom species as the graph "
        "node attribute.",
    )
    coord_hash: str | None = Field(
        None,
        description="Weisfeiler Lehman (WL) graph hash using the atom coordinates as the graph "
        "node attribute.",
    )

    # TODO - type of `tags` field seems to differ among task databases
    # sometimes List, sometimes Dict
    # left as Any here to ensure tags don't cause validation to fail.
    tags: Any | None = Field(None, description="Metadata tags")

    warnings: dict[str, bool] | None = Field(
        None, description="Any warnings related to this task document"
    )

    @property
    def level_of_theory(self) -> LevelOfTheory:
        return level_of_theory(self.orig)

    @property
    def solvent(self) -> str:
        return solvent(self.orig, custom_smd=self.custom_smd)

    @property
    def lot_solvent(self) -> str:
        return lot_solvent_string(self.orig, custom_smd=self.custom_smd)

    @property
    def task_type(self) -> TaskType:
        return task_type(self.orig, special_run_type=self.special_run_type)

    @property
    def calc_type(self) -> CalcType:
        return calc_type(self.special_run_type, self.orig)

    @property
    def entry(self) -> dict[str, Any]:
        mol = None
        for mol_field in ("optimized_molecule", "initial_molecule"):
            if mol := getattr(self.output, mol_field, None):
                break
        else:
            raise ValueError("No molecule could be associated with the calculation.")

        charge = int(mol.charge) if self.charge is None else int(self.charge)
        spin = (
            mol.spin_multiplicity
            if self.spin_multiplicity is None
            else self.spin_multiplicity
        )

        entry_dict = {
            "entry_id": self.task_id,
            "task_id": self.task_id,
            "charge": charge,
            "spin_multiplicity": spin,
            "level_of_theory": self.level_of_theory,
            "solvent": self.solvent,
            "lot_solvent": self.lot_solvent,
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
            "species_hash": self.species_hash,
            "coord_hash": self.coord_hash,
        }

        return entry_dict


def filter_task_type(
    entries: list[dict[str, Any]],
    task_type: TaskType,
    sort_by: Callable | None = None,
) -> list[dict[str, Any]]:
    """
    Filter (and sort) TaskDocument entries based on task type

    :param entries: List of TaskDocument entry dicts
    :param TaskType: TaskType to accept
    :param sort_by: Function used to sort (default None)
    :return: Filtered (sorted) list of entries
    """

    filtered = [f for f in entries if f["task_type"] == task_type]
    return sorted(filtered, key=sort_by) if sort_by is not None else filtered
