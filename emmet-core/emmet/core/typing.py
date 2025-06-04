"""Define custom type annotations for emmet-core."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal, TypeAlias

from pymatgen.core import Structure
from pymatgen.electronic_structure.bandstructure import Kpoint
from typing_extensions import TypedDict

from emmet.core import ARROW_COMPATIBLE

if ARROW_COMPATIBLE:
    from emmet.core.serialization_adapters.structure_adapter import AnnotatedStructure


############################################################
# ALIASES
############################################################
PathLike: TypeAlias = str | Path | os.DirEntry[str]
"""Type of a generic path-like object"""

StructureType: TypeAlias = AnnotatedStructure if ARROW_COMPATIBLE else Structure


############################################################
# ALLOYS
############################################################
class TypedBoolDict(TypedDict):
    min: bool
    max: bool


class TypedRangeDict(TypedDict):
    min: float
    max: float


class TypedSearchDict(TypedDict):
    alloying_element: list[str]
    band_gap: TypedRangeDict
    energy_above_hull: TypedRangeDict
    formation_energy_per_atom: TypedRangeDict
    formula: list[str]
    id: list[str]
    is_gap_direct: TypedBoolDict
    member_ids: list[str]
    spacegroup_intl_number: TypedRangeDict
    theoretical: TypedBoolDict
    volume_cube_root: TypedRangeDict


############################################################
# BONDS
############################################################
class TypedBondLengthStatsDict(TypedDict):
    all_weights: list[float]
    min: float
    max: float
    mean: float
    variance: float


############################################################
# ELECTRONIC STRUCTURE
############################################################
StrSpin: TypeAlias = Literal["1", "-1"]
StrOrbital: TypeAlias = Literal["total", "s", "p", "d", "f"]


class TypedBandDict(TypedDict):
    band_index: dict[str, list[int]]
    kpoint_index: list[int]
    kpoint: Kpoint
    energy: float
    projections: dict[str, list[list[float]]]


class TypedBandGapDict(TypedDict):
    direct: bool
    transition: str
    energy: float


class TypedBranchDict(TypedDict):
    start_index: int
    end_index: int
    name: str


############################################################
# EOS
############################################################
class TypedEOSDict(TypedDict):
    V0: float
    eos_energies: list[float]
    B: float
    C: float
    E0: float


############################################################
# OPTIMADE
############################################################
class TypedStabilityDict(TypedDict):
    thermo_id: str
    energy_above_hull: float
    formation_energy_per_atom: float
    last_updated_thermo: datetime


############################################################
# PHONON
############################################################
vec2D: TypeAlias = list[float, float]
vec3D: TypeAlias = list[float, float, float]


class PhononWebsiteDict(TypedDict):
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


############################################################
# USER SETTINGS
############################################################
class TypedUserSettingsDict(TypedDict):
    institution: str
    sector: str
    job_role: str
    is_email_subscribed: bool
    message_last_read: datetime
    agreed_terms: bool
