""" Core definition of a Q-Chem calculation output """

from typing import List

from pydantic import BaseModel, Field

from emmet.stubs import Vector3D, Molecule
from emmet.core.qchem.bonding import Bonding


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

    vibrational_frequency_modes: List[List[Vector3D]] = Field(
        None, description="Frequency mode vectors for this molecule"
    )

    modes_ir_active: List[bool] = Field(
        None,
        description="Determination of if each mode should be considered in IR spectra",
    )

    modes_ir_intensity: List[float] = Field(
        None, description="IR intensity of vibrational frequency modes"
    )

    mulliken_charges: List[float] = Field(
        None,
        description="Partial charges on each atom, as determined by Mulliken population analysis",
    )

    mulliken_spin: List[float] = Field(
        None,
        description="Spin on each atom, as determined by Mulliken population analysis"
    )

    resp_charges: List[float] = Field(
        None,
        description="Molecule partial charges, as determined by the "
                    "Restrained Electrostatic Potential (RESP) method",
    )

    bonding: Bonding = Field(
        None,
        description="Bonding information, obtained via critical point analysis or "
                    "heuristic algorithms."
    )

    walltime: float = Field(None, description="The real time elapsed in seconds")

    cputime: float = Field(None, description="The system CPU time in seconds")
