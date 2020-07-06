from pydantic import BaseModel, Field
from typing import List, Tuple, Optional
from emmet.stubs import Structure
from emmet.stubs import Matrix3D, Vector3D
from emmet.core.polar import Dielectric


class PhononWarnings(BaseModel):
    """
    Definition of the possible warnings associated with a phonon document.
    """
    large_asr_break: bool = Field(
        None, description="True if acoustic sum rule max breaking is larger "
                          "than 30 cm^-1."
    )

    large_cnsr_break: bool = Field(
        None, description="True if charge neutrality sum rule max breaking "
                          "is larger than 0.2."
    )

    has_neg_fr: bool = Field(
        None, description="True if the phonon band structure has negative "
                          "frequencies anywhere in the Brillouin zone."
    )

    small_q_neg_fr: bool = Field(
        None,
        description="True if the phonon band structure has negative frequencies,"
                    " but these are small and very close to the Gamma point "
                    "(usually related to numerical errors)."
    )


class ThermodynamicProperties(BaseModel):
    """
    Definition of the thermodynamic properties extracted from the phonon frequencies.
    """

    temperatures: List[float] = Field(
        ...,
        description="The list of temperatures at which the thermodynamic properties "
                    "are calculated"
    )

    cv: List[float] = Field(
        ...,
        description="The values of the constant-volume specific heat."
    )

    entropy: List[float] = Field(
        ...,
        description="The values of the vibrational entropy."
    )

    internal_energy: List[float] = Field(
        ...,
        description="The values of the phonon contribution to the internal energy."
    )

    helmholtz_free_energy: List[float] = Field(
        ...,
        description="The values of the Helmholtz free energy."
    )


class Phonon(BaseModel):
    """
    Definition for a document with data produced by a phonon calculation.
    """

    material_id: str = Field(
        ...,
        description="The ID of this material, in the form: mp-******",
    )

    structure: Structure = Field(
        ..., description="The relaxed structure for the phonon calculation."
    )

    cnsr_break: float = Field(
        None, description="The maximum breaking of the charge nutrality sum "
                          "rule (CNSR) in the Born effective charges."
    )

    asr_break: float = Field(
        None, description="The maximum breaking of the acoustic sum rule (ASR)."
    )

    warnings: PhononWarnings = Field(
        None,
        description="The potential warnings associated to the phonon calculation."
    )

    dielectric: Dielectric = Field(
        None,
        description="Dielectric properties obtained during a phonon calculations."
    )

    becs: List[Matrix3D] = Field(
        None,
        description="Born effective charges calculated for a phonon calculation."
    )

    dos: dict = Field(
        None,
        description="Serialized version of a pymatgen CompletePhononDos object."
    )

    band_structure: dict = Field(
        None, description="Serialized version of a pymatgen "
                          "PhononBandStructureSymmLine object."
    )

    phonon_website: dict = Field(
        None, description="Phononwebsite dictionary to plot the animated "
                          "phonon modes."
    )

    ir_spectra: dict = Field(
        None,
        description="Serialized version of a pymatgen IRDielectricTensor object."
    )

    thermodynamic: ThermodynamicProperties = Field(
        None,
        description="The thermodynamic properties extracted from the phonon "
                    "frequencies."
    )


class AbinitPhonon(Phonon):
    """
    Definition for a document with data produced from a phonon calculation
    with Abinit.
    """
    abinit_input_vars: dict = Field(
        None,
        description="Dict representation of the inputs used to obtain the phonon"
                    "properties and the main general options (e.g. number of "
                    "k-points, number of q-points)."
    )

    ddb_file: str = Field(
        None, description="The string of the DDB file."
    )

    dos_method: str = Field(
        None, description="The method used to calculate the phonon DOS."
    )

    msqd_dos: dict = Field(
        None,
        description="Data for the generalized DOS and thermal displacements."
    )


class SoundVelocity(BaseModel):
    """
    Definition for a document with the sound velocities of the acoustic modes
    close to Gamma, as obtained from a phonon calculation.
    """

    material_id: str = Field(
        ...,
        description="The ID of this material, in the form: mp-******",
    )

    structure: Structure = Field(
        ..., description="The relaxed structure for the phonon calculation."
    )

    directions: List[Vector3D] = Field(
        ...,
        description="Q-points identifying the directions for the calculation"
                    "of the speed of sound. In fractional coordinates.",
    )

    labels: List[Optional[str]] = Field(
        ..., description="labels of the directions."
    )

    sound_velocities: List[Vector3D] = Field(
        ...,
        description="Values of the sound velocities in SI units.",
    )

    mode_types: List[Tuple[Optional[str], Optional[str], Optional[str]]] = Field(
        ...,
        description="The types of the modes ('transversal', 'longitudinal'). "
                    "None if not correctly identified.",
    )
