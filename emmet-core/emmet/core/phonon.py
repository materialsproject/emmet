from datetime import datetime
from typing import Optional, Tuple

from pydantic import BaseModel, Field, field_validator
from pymatgen.core import Structure
from pymatgen.phonon.bandstructure import PhononBandStructureSymmLine
from pymatgen.phonon.dos import PhononDos as PhononDosObject
from typing_extensions import Literal, TypedDict

from emmet.core.common import convert_datetime
from emmet.core.math import Tensor4R, Vector3D
from emmet.core.mpid import MPID
from emmet.core.polar import BornEffectiveCharges, DielectricDoc, IRDielectric
from emmet.core.structure import StructureMetadata
from emmet.core.utils import DocEnum, utcnow


class PhononBSDOSDoc(BaseModel):
    """
    Phonon band structures and density of states data.
    """

    material_id: MPID | None = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )

    ph_bs: Optional[PhononBandStructureSymmLine] = Field(
        None,
        description="Phonon band structure object.",
    )

    ph_dos: Optional[PhononDosObject] = Field(
        None,
        description="Phonon density of states object.",
    )

    last_updated: datetime = Field(
        default_factory=utcnow,
        description="Timestamp for the most recent calculation for this Material document.",
    )

    # Make sure that the datetime field is properly formatted
    @field_validator("last_updated", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)


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


class PhononBandStructure(BaseModel):
    """
    Document with a pymatgen serialized phonon band structure.
    """

    material_id: str = Field(
        ...,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******",
    )

    doc_type: Literal["bs"] = Field(
        "bs", description="The type of the document: a phonon band structure."
    )

    band_structure: PhononBandStructureSymmLine | None = Field(
        None,
        description="Serialized version of a pymatgen "
        "PhononBandStructureSymmLine object.",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=utcnow,
    )


class PhononDos(BaseModel):
    """
    Document with a pymatgen serialized phonon density of states (DOS).
    """

    material_id: str = Field(
        ...,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******",
    )

    doc_type: Literal["dos"] = Field(
        "dos", description="The type of the document: a phonon density of states."
    )

    dos: PhononDosObject | None = Field(
        None, description="Serialized version of a pymatgen CompletePhononDos object."
    )

    dos_method: Optional[str] = Field(
        None, description="The method used to calculate the phonon DOS."
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=utcnow,
    )


class PhononWebsiteDict(TypedDict):
    vec2D = list[float, float]
    vec3D = list[float, float, float]

    atom_numbers: list[int]
    atom_pos_car: list[vec3D]
    atom_pos_red: list[vec3D]
    atom_types: list[str]
    distances: list[float]
    eigenvalues: list[list[float]]
    formula: str
    # fails arrow conversion
    # highsym_qpts: list[list[int, str]]
    lattice: list[vec3D]
    line_breaks: list[tuple[int, int]]
    name: str
    natoms: int
    qpoints: list[vec3D]
    repetitions: list[int, int, int]
    vectors: list[list[list[list[vec2D, vec2D, vec2D]]]]


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

    phononwebsite: PhononWebsiteDict | None = Field(
        None,
        description="Phononwebsite dictionary to plot the animated " "phonon modes.",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=utcnow,
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

    ddb: Optional[str] = Field(None, description="The string of the DDB file.")

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=utcnow,
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
        None, description="list of warnings associated to the phonon calculation."
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
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=utcnow,
    )


class TypedBaseInputDict(TypedDict):
    charge: float
    chksymbreak: int
    ecut: float
    fband: float
    kptopt: int
    nband: int
    nbdbuf: int
    ngkpt: list[int]
    nshiftk: int
    nspden: int
    nspinor: int
    nsppol: int
    nstep: int
    pawecutdg: float
    shiftk: list[list[float]]
    tolvrs: float


class TypedDdBaseDict(TypedBaseInputDict):
    chkprim: int
    nqpt: int
    qpt: list[int]
    rfdir: list[int]
    rfelfd: int


class TypedDdeInputDict(TypedDdBaseDict):
    prtwf: int


class TypedDdkInputDict(TypedDdBaseDict):
    iscf: float


class TypedPhononInputDict(TypedDdeInputDict):
    rfatpol: list[int]


class TypedPseudopotentialsDict(TypedDict):
    md5: list[str]
    name: list[str]


class TypedAbinitInputVars(TypedDict):
    dde_input: TypedDdeInputDict
    ddk_input: TypedDdkInputDict
    ecut: float
    gs_input: TypedBaseInputDict
    ngkpt: list[int]
    ngqpt: list[int]
    occopt: int
    phonon_input: TypedPhononInputDict
    pseudopotentials: TypedPseudopotentialsDict
    shiftk: list[list[float]]
    tsmear: int
    wfq_input: TypedBaseInputDict  # have to guess here without an example entry


class AbinitPhonon(Phonon):
    """
    Definition for a document with data produced from a phonon calculation
    with Abinit.
    """

    abinit_input_vars: TypedAbinitInputVars | None = Field(
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

    mode_types: list[Tuple[Optional[str], Optional[str], Optional[str]]] = Field(
        ...,
        description="The types of the modes ('transversal', 'longitudinal'). "
        "None if not correctly identified.",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=utcnow,
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
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=utcnow,
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

    amu: dict[str, float] = Field(
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
