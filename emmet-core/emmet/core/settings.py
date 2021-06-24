"""
Settings for defaults in the core definitions of Materials Project Documents
"""
import json
from pathlib import Path
from typing import Dict, List, Type, TypeVar, Union

import requests
from pydantic import BaseSettings, Field, root_validator
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

    MAX_PIEZO_MILLER: int = Field(
        10,
        description="Maximum miller allowed for computing strain direction for maximal piezo response",
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
            "GGA Static": "pymatgen.io.vasp.sets.MPStaticSet",
            "GGA+U Static": "pymatgen.io.vasp.sets.MPStaticSet",
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

    def as_dict(self):
        """
        HotPatch to enable serializing EmmetSettings via Monty
        """
        return self.dict(exclude_unset=True, exclude_defaults=True)

    @classmethod
    def from_dict(cls: Type[S], settings: Dict) -> S:
        """
        HotPatch to enable serializing EmmetSettings via Monty
        """
        return cls(**settings)
