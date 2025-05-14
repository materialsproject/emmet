from __future__ import annotations

from datetime import datetime
from functools import cached_property

import numpy as np
from pydantic import model_validator, BaseModel, Field, computed_field
from typing import Optional, TYPE_CHECKING

from emmet.core.mpid import MPID
from pymatgen.phonon.bandstructure import PhononBandStructureSymmLine
from pymatgen.phonon.dos import PhononDos as PhononDosObject

from emmet.core.utils import DocEnum
from pymatgen.core import Structure
from emmet.core.math import Vector3D, Matrix3D, Tensor4R
from emmet.core.polar import DielectricDoc, BornEffectiveCharges, IRDielectric
from emmet.core.structure import StructureMetadata
from emmet.core.common import convert_datetime
from emmet.core.utils import utcnow

from typing_extensions import Literal

if TYPE_CHECKING:
    from typing import Any

class PhononDOS(BaseModel):
    """Define schema of pymatgen phonon density of states."""

    frequencies : list[float] = Field(description="The phonon frequencies in THz.")
    densities : list[float] = Field(description="The phonon density of states.")
    
    def to_pmg(self) -> PhononDosObject:
        return PhononDosObject(
            frequencies=self.frequencies, densities=self.densities
        )

class PhononBS(BaseModel):
    """Define schema of pymatgen phonon band structure."""

    qpoints : list[Vector3D] = Field(None,description="The q-kpoints at which the band structure was sampled, in direct coordinates.")
    frequencies : list[tuple[float,float]] = Field(None, description="The phonon frequencies in THz, with the first index representing the band, and the second the q-point.")
    reciprocal_lattice : tuple[Vector3D,Vector3D,Vector3D] = Field(description="The reciprocal lattice.")
    has_nac : bool = Field(False,description="Whether the calculation includes non-analytical corrections at Gamma.")
    eigendisplacements : list[list[list[tuple[complex,complex,complex]]]] | None = Field(None,description="Phonon eigendisplacements in Cartesian coordinates.")
    labels_dict: dict[str,Vector3D] | None = Field(None, description="The high-symmetry labels of specific q-points.")
    structure : Structure | None = Field(None, description="The structure associated with the calculation.")

    @model_validator(mode="before")
    def rehydrate(cls, config : Any) -> Any:
        if (egd := config.get("eigendisplacements")) and all(
            egd.get(k) is not None for k in ("real","imag")
        ):
            config["eigendisplacements"] = (np.array(egd["real"]) + 1j*np.array(egd["imag"])).tolist()
            
        if (struct := config.get("structure")) and not isinstance(struct,Structure):
            config["structure"] = Structure.from_dict(struct)

        # remap legacy fields
        for k, v in {
            "lattice_rec": "reciprocal_lattice",
        }.items():
            if config.get(k):
                config[v] = config.pop(k)

        if isinstance(config["reciprocal_lattice"],dict):
            config["reciprocal_lattice"] = config["reciprocal_lattice"].get("matrix")

        return config
    
    def to_pmg(self) -> PhononBandStructureSymmLine:
        return PhononBandStructureSymmLine(
            self.qpoints,
            self.frequencies,
            self.reciprocal_lattice,
            has_nac= self.has_nac,
            eigendisplacements=self.eigendisplacements,
            structure=self.structure,
            labels_dict=self.labels_dict,
            coords_are_cartesian=False,
        )
        
class BasePhononBSDOSDoc(StructureMetadata):
    """Phonon band structures and density of states data."""

    material_id: MPID | None = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )

    phonon_bandstructure : PhononBS | None = Field(
        None,
        description="Phonon band structure object.",
    )

    phonon_dos: PhononDOS | None = Field(
        None,
        description="Phonon density of states object.",
    )

    epsilon_static: Matrix3D | None = Field(
        None, description="The high-frequency dielectric constant."
    )

    epsilon_electronic: Matrix3D | None = Field(
        None, description="The electronic contribution to the high-frequency dielectric constant."
    )

    born: list[Matrix3D] | None = Field(
        None,
        description="Born charges, only for symmetrically inequivalent atoms",
    )


    last_updated: datetime = Field(
        utcnow,
        description="Timestamp for the most recent calculation for this Material document.",
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_fields(cls, config : Any) -> Any:
        """Migrate legacy input fields."""
        for k, v in {
            "ph_dos": "phonon_dos",
            "ph_bs": "phonon_bandstructure",
            "e_total": "epsilon_static",
            "e_electronic": "epsilon_electronic",
            "becs": "born",
        }.items():
            if config.get(k):
                config[v] = config.pop(k)

        # Make sure that the datetime field is properly formatted
        if config.get("last_updated"):
            config["last_updated"] = convert_datetime(cls, config["last_updated"])
        return config
    
    @computed_field
    @cached_property
    def charge_neutral_sum_rule(self) -> list[float]:
        """Sum of Born effective charges over sites should be zero."""
        if self.born is None:
            return []
        bec = np.array(self.born)
        return np.sum(bec,axis=0).tolist()

    # @computed_field
    # @cached_property
    # def acoustic_sum_rule(self) -> list[float]:
    #     """Sum of Born effective charges over sites should be zero."""

class PhononComputationalSettings(BaseModel):
    """Collection to store computational settings for the phonon computation."""

    # could be optional and implemented at a later stage?
    npoints_band: int | None = Field(None, description="number of points for band structure computation")
    kpath_scheme: str | None = Field(None,description = "indicates the kpath scheme")
    kpoint_density_dos: int | None= Field(
        None, description = "number of points for computation of free energies and densities of states",
    )

class ThermalDisplacementData(BaseModel):
    """Collection to store information on the thermal displacement matrices."""

    freq_min_thermal_displacements: float | None = Field(None,
        description = "cutoff frequency in THz to avoid numerical issues in the "
        "computation of the thermal displacement parameters"
    )
    thermal_displacement_matrix_cif: list[list[Matrix3D]] | None = Field(
        None, description="field including thermal displacement matrices in CIF format"
    )
    thermal_displacement_matrix: list[list[Matrix3D]] | None = Field(
        None,
        description="field including thermal displacement matrices in Cartesian "
        "coordinate system",
    )
    temperatures_thermal_displacements: list[float] | None = Field(
        None,
        description="temperatures at which the thermal displacement matrices"
        "have been computed",
    )

class PhononUUIDs(BaseModel):
    """Collection to save all uuids connected to the phonon run."""

    optimization_run_uuid: str | None = Field(
        None, description="optimization run uuid"
    )
    displacements_uuids: list[str] | None = Field(
        None, description="The uuids of the displacement jobs."
    )
    static_run_uuid: str | None = Field(None, description="static run uuid")
    born_run_uuid: str | None = Field(None, description="born run uuid")

class PhononJobDirs(BaseModel):
    """Collection to save all job directories relevant for the phonon run."""

    displacements_job_dirs: list[str | None] | None = Field(
        None, description="The directories where the displacement jobs were run."
    )
    static_run_job_dir: str | None = Field(
        None, description="Directory where static run was performed."
    )
    born_run_job_dir: str | None = Field(
        None, description="Directory where born run was performed."
    )
    optimization_run_job_dir: str | None = Field(
        None, description="Directory where optimization run was performed."
    )
    taskdoc_run_job_dir: str | None = Field(
        None, description="Directory where task doc was generated."
    )



class PhononBSDOSDoc(BasePhononBSDOSDoc):
    """Heavier phonon document schema for parsing newer phonon calculations."""

    structure: Structure | None = Field(
        None, description="Structure used in the calculation."
    )

    free_energies: list[float] | None = Field(
        None,
        description="vibrational part of the free energies in J/mol per "
        "formula unit for temperatures in temperature_list",
    )

    heat_capacities: list[float] | None = Field(
        None,
        description="heat capacities in J/K/mol per "
        "formula unit for temperatures in temperature_list",
    )

    internal_energies: list[float] | None = Field(
        None,
        description="internal energies in J/mol per "
        "formula unit for temperatures in temperature_list",
    )
    entropies: list[float] | None = Field(
        None,
        description="entropies in J/(K*mol) per formula unit"
        "for temperatures in temperature_list ",
    )

    temperatures: list[float] | None = Field(
        None,
        description="temperatures at which the vibrational"
        " part of the free energies"
        " and other properties have been computed",
    )

    total_dft_energy: float | None = Field(
        None, description="total DFT energy per formula unit in eV"
    )

    volume_per_formula_unit: float | None = Field(
        None, description="volume per formula unit in Angstrom**3"
    )

    formula_units: int | None = Field(None, description="Formula units per cell")

    has_imaginary_modes: Optional[bool] = Field(
        None, description="if true, structure has imaginary modes"
    )

    # needed, e.g. to compute Grueneisen parameter etc
    force_constants: list[list[Matrix3D]] | None = Field(
        None, description="Force constants between every pair of atoms in the structure"
    )

    supercell_matrix: Optional[Matrix3D] = Field(
        None, description="matrix describing the supercell"
    )
    primitive_matrix: Optional[Matrix3D] = Field(
        None, description="matrix describing relationship to primitive cell"
    )

    code: Optional[str] = Field(
        None, description="String describing the code for the computation"
    )

    phonopy_settings: Optional[PhononComputationalSettings] = Field(
        None, description="Field including settings for Phonopy"
    )

    thermal_displacement_data: Optional[ThermalDisplacementData] = Field(
        None,
        description="Includes all data of the computation of the thermal displacements",
    )

    jobdirs: Optional[PhononJobDirs] = Field(
        None, description="Field including all relevant job directories"
    )

    uuids: Optional[PhononUUIDs] = Field(
        None, description="Field including all relevant uuids"
    )


class PhononWarnings(DocEnum):
    ASR = "ASR break", "acoustic sum rule max breaking is larger than 30 cm^-1."
    CNSR = "CNSR break", "charge neutrality sum rule max breaking is larger than 0.2."
    NEG_FREQ = (
        "has negative frequencies",
        "phonon band structure has negative "
        "frequencies anywhere in the Brillouin zone.",
    )
    SMALL_Q_NEG_FREQ = (
        "has small q negative frequencies",
        "the phonon band structure has negative frequencies,"
        " but these are small and very close to the Gamma point "
        "(usually related to numerical errors).",
    )

class PhononWebsiteBS(BaseModel):
    """
    Document with a serialized version of the phonon band structure suitable
    for the phononwebsite (http://henriquemiranda.github.io/phononwebsite/).
    """

    material_id: str = Field(
        ...,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******",
    )

    doc_type: Literal["phononwebsite"] = Field(
        "phononwebsite",
        description="The type of the document: a phonon band structure for the phononwebsite.",
    )

    phononwebsite: dict | None = Field(
        None,
        description="Phononwebsite dictionary to plot the animated " "phonon modes.",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=datetime.utcnow,
    )


class Ddb(BaseModel):
    """
    Document with a the string version of the DDB file produced by abinit.
    """

    material_id: str = Field(
        ...,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******",
    )

    doc_type: Literal["ddb"] = Field(
        "ddb", description="The type of the document: a DDB file."
    )

    ddb: str | None = Field(None, description="The string of the DDB file.")

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=datetime.utcnow,
    )


class ThermodynamicProperties(BaseModel):
    """
    Definition of the thermodynamic properties extracted from the phonon frequencies.
    """

    temperatures: list[float] = Field(
        ...,
        description="The list of temperatures at which the thermodynamic properties "
        "are calculated",
    )

    cv: list[float] = Field(
        ...,
        description="The values of the constant-volume specific heat.",
        alias="heat_capacity",
    )

    entropy: list[float] = Field(
        ..., description="The values of the vibrational entropy."
    )


class VibrationalEnergy(BaseModel):
    """
    Definition of the vibrational contribution to the energy as function of
    the temperature.
    """

    temperatures: list[float] = Field(
        ...,
        description="The list of temperatures at which the thermodynamic properties "
        "are calculated",
    )

    internal_energy: list[float] = Field(
        ..., description="The values of the phonon contribution to the internal energy."
    )

    helmholtz_free_energy: list[float] = Field(
        ..., description="The values of the Helmholtz free energy."
    )

    zero_point_energy: float = Field(
        ..., description="The value of the zero point energy."
    )


class Phonon(StructureMetadata):
    """
    Definition for a document with data produced by a phonon calculation.
    """

    material_id: str = Field(
        ...,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******",
    )

    structure: Structure = Field(
        ..., description="The relaxed structure for the phonon calculation."
    )

    asr_break: Optional[float] = Field(
        None, description="The maximum breaking of the acoustic sum rule (ASR)."
    )

    warnings: Optional[list[PhononWarnings]] = Field(
        None, description="List of warnings associated to the phonon calculation."
    )

    dielectric: Optional[DielectricDoc] = Field(
        None, description="Dielectric properties obtained during a phonon calculations."
    )

    becs: Optional[BornEffectiveCharges] = Field(
        None, description="Born effective charges obtained for a phonon calculation."
    )

    ir_spectra: Optional[IRDielectric] = Field(
        None, description="The IRDielectricTensor."
    )

    thermodynamic: Optional[ThermodynamicProperties] = Field(
        None,
        description="The thermodynamic properties extracted from the phonon "
        "frequencies.",
    )

    vibrational_energy: Optional[VibrationalEnergy] = Field(
        None, description="The vibrational contributions to the total energy."
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=datetime.utcnow,
    )


class AbinitPhonon(Phonon):
    """
    Definition for a document with data produced from a phonon calculation
    with Abinit.
    """

    abinit_input_vars: Optional[dict] = Field(
        None,
        description="Dict representation of the inputs used to obtain the phonon"
        "properties and the main general options (e.g. number of "
        "k-points, number of q-points).",
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

    directions: list[Vector3D] = Field(
        ...,
        description="Q-points identifying the directions for the calculation"
        "of the speed of sound. In fractional coordinates.",
    )

    labels: list[Optional[str]] = Field(..., description="labels of the directions.")

    sound_velocities: list[Vector3D] = Field(
        ...,
        description="Values of the sound velocities in SI units.",
    )

    mode_types: list[tuple[Optional[str], Optional[str], Optional[str]]] = Field(
        ...,
        description="The types of the modes ('transversal', 'longitudinal'). "
        "None if not correctly identified.",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=datetime.utcnow,
    )


class ThermalDisplacement(BaseModel):
    """
    Definition of a Document for the generalized density of states and
    mean square displacements related to phonon oscillations.
    """

    material_id: str = Field(
        ...,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=datetime.utcnow,
    )

    nsites: int = Field(
        ...,
        description="The number of sites in the structure.",
    )

    nomega: int = Field(
        ...,
        description="The number of frequencies.",
    )

    ntemp: int = Field(
        ...,
        description="The number of temperatures for which the displacements are calculated",
    )

    temperatures: list[float] = Field(
        ...,
        description="The list of temperatures at which the thermodynamic properties "
        "are calculated",
    )

    frequencies: list[float] = Field(
        ..., description="The list of frequencies for the generalized DOS"
    )

    gdos_aijw: Tensor4R = Field(
        ...,
        description=" Generalized DOS in Cartesian coords, with shape (nsites, 3, 3, nomega)",
    )

    amu: dict = Field(
        ..., description="Dictionary of the atomic masses in atomic units."
    )

    structure: Structure = Field(
        ..., description="The relaxed structure for the phonon calculation."
    )

    ucif_t: Tensor4R = Field(
        ...,
        description="Mean squared displacement U tensors as a function of T for T in tmesh in CIF format."
        "With shape (natom, 3, 3, ntemp) ",
    )
    ucif_string_t300k: str = Field(
        ...,
        description="Mean squared displacement U tensors at T=300K in CIF string format.",
    )
