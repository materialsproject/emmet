"""
Settings for defaults in the core definitions of Materials Project Documents
"""
import json
from pathlib import Path
from typing import Dict, List, Type, TypeVar, Union

import requests
from monty.json import MontyDecoder
from pydantic import BaseSettings, Field, root_validator
from pydantic.class_validators import validator
from pydantic.types import PyObject

DEFAULT_CONFIG_FILE_PATH = str(Path.home().joinpath(".emmet.json"))


S = TypeVar("S", bound="EmmetSettings")


class EmmetSettings(BaseSettings):
    """
    Settings for the emmet- packages
    Non-core packages should subclass this to get settings specific to their needs
    The default way to modify these is to modify ~/.emmet.json or set the environment variable
    EMMET_CONFIG_FILE to point to the json with emmet settings
    """

    config_file: str = Field(
        DEFAULT_CONFIG_FILE_PATH, description="File to load alternative defaults from"
    )

    LTOL: float = Field(
        0.2, description="Fractional length tolerance for structure matching"
    )
    STOL: float = Field(
        0.3,
        description="Site tolerance for structure matching. Defined as the fraction of the"
        " average free length per atom = ( V / Nsites ) ** (1/3)",
    )
    SYMPREC: float = Field(
        0.1, description="Symmetry precision for spglib symmetry finding"
    )
    ANGLE_TOL: float = Field(
        5, description="Angle tolerance for structure matching in degrees."
    )

    PGATOL: float = Field(
        0.3,
        description="Distance tolerance to consider sites as symmetrically equivalent.",
    )
    PGAEIGENTOL: float = Field(
        0.01, description="Tolerance to compare eigen values of the inertia tensor."
    )
    PGAMATRIXTOL: float = Field(
        0.1,
        description="Tolerance used to generate the full set of symmetry operations of the point group.",
    )

    MAX_PIEZO_MILLER: int = Field(
        10,
        description="Maximum miller allowed for computing strain direction for maximal piezo response",
    )

    QCHEM_FUNCTIONAL_QUALITY_SCORES: Dict[str, int] = Field(
        {
            "wB97M-V": 7,
            "wB97X-V": 6,
            "wB97X-D3": 5,
            "wB97X-D": 5,
            "B3LYP": 4,
            "B97M-rV": 3,
            "B97-D3": 2,
            "B97-D": 2,
            "PBE": 1,
        },
        description="Dictionary mapping Q-Chem density functionals to a quality score.",
    )

    QCHEM_BASIS_QUALITY_SCORES: Dict[str, int] = Field(
        {
            "6-31g*": 1,
            "def2-SVPD": 2,
            "def2-TZVP": 3,
            "def2-TZVPD": 4,
            "def2-TZVPP": 5,
            "def2-TZVPPD": 6,
            "def2-QZVPPD": 7,
        },
        description="Dictionary mapping Q-Chem basis sets to a quality score.",
    )

    QCHEM_SOLVENT_MODEL_QUALITY_SCORES: Dict[str, int] = Field(
        {"CMIRS": 7, "SMD": 5, "ISOSVP": 4, "PCM": 3, "VACUUM": 1},
        description="Dictionary mapping Q-Chem solvent models to a quality score.",
    )

    QCHEM_TASK_QUALITY_SCORES: Dict[str, int] = Field(
        {"geometry optimization": 1, "frequency-flattening geometry optimization": 2},
        description="Dictionary mapping Q-Chem task type to a quality score",
    )

    VASP_QUALITY_SCORES: Dict[str, int] = Field(
        {"SCAN": 3, "GGA+U": 2, "GGA": 1},
        description="Dictionary Mapping VASP calculation run types to rung level for VASP materials builders",
    )

    VASP_KPTS_TOLERANCE: float = Field(
        0.9,
        description="Relative tolerance for kpt density to still be a valid task document",
    )

    VASP_KSPACING_TOLERANCE: float = Field(
        0.05,
        description="Relative tolerance for kspacing to still be a valid task document",
    )

    VASP_DEFAULT_INPUT_SETS: Dict[str, PyObject] = Field(
        {
            "GGA Structure Optimization": "pymatgen.io.vasp.sets.MPRelaxSet",
            "GGA+U Structure Optimization": "pymatgen.io.vasp.sets.MPRelaxSet",
            "R2SCAN Structure Optimization": "pymatgen.io.vasp.sets.MPScanRelaxSet",
            "SCAN Structure Optimization": "pymatgen.io.vasp.sets.MPScanRelaxSet",
            "PBESol Structure Optimization": "pymatgen.io.vasp.sets.MPScanRelaxSet",
            "GGA Static": "pymatgen.io.vasp.sets.MPStaticSet",
            "GGA+U Static": "pymatgen.io.vasp.sets.MPStaticSet",
            "R2SCAN Static": "pymatgen.io.vasp.sets.MPScanStaticSet",
            "SCAN Static": "pymatgen.io.vasp.sets.MPScanStaticSet",
            "PBESol Static": "pymatgen.io.vasp.sets.MPScanStaticSet",
        },
        description="Default input sets for task validation",
    )

    VASP_CHECKED_LDAU_FIELDS: List[str] = Field(
        ["LDAUU", "LDAUJ", "LDAUL"], description="LDAU fields to validate for tasks"
    )

    VASP_MAX_SCF_GRADIENT: float = Field(
        100,
        description="Maximum upward gradient in the last SCF for any VASP calculation",
    )

    VASP_USE_STATICS: bool = Field(
        True,
        description="Use static calculations for structure and energy along with structure optimizations",
    )

    class Config:
        env_prefix = "emmet_"
        extra = "ignore"

    @root_validator(pre=True)
    def load_default_settings(cls, values):
        """
        Loads settings from a root file if available and uses that as defaults in
        place of built in defaults
        """
        config_file_path: str = values.get("config_file", DEFAULT_CONFIG_FILE_PATH)

        new_values = {}

        if config_file_path.startswith("http"):
            new_values = requests.get(config_file_path).json()
        elif Path(config_file_path).exists():
            with open(config_file_path) as f:
                new_values = json.load(f)

        new_values.update(values)

        return new_values

    @classmethod
    def autoload(cls: Type[S], settings: Union[None, dict, S]) -> S:
        if settings is None:
            return cls()
        elif isinstance(settings, dict):
            return cls(**settings)
        return settings

    @validator("VASP_DEFAULT_INPUT_SETS", pre=True)
    def convert_input_sets(cls, value):
        if isinstance(value, dict):
            return {k: MontyDecoder().process_decoded(v) for k, v in value.items()}
        return value

    def as_dict(self):
        """
        HotPatch to enable serializing EmmetSettings via Monty
        """
        return self.dict(exclude_unset=True, exclude_defaults=True)
