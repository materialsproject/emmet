"""
This file defines any arbitrary global variables used in Materials Project
database building and in the website code, to ensure consistency between
different modules and packages.
"""
import importlib
import json
from typing import Dict, List, Optional

import requests
from pydantic import BaseSettings, Field, root_validator, validator
from pydantic.types import Path

DEFAULT_CONFIG_FILE_PATH = str(Path.home().joinpath(".emmet.json"))


class EmmetSettings(BaseSettings):
    """
    Settings for the emmet- packages
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

    TAGS_TO_SANDBOXES: Optional[Dict[str, List[str]]] = Field(
        None,
        description="Mapping of calcuation tags to sandboxes: Dict[sandbox, list of tags]."
        " Any calculation without these tags will be kept as core.",
    )

    VASP_SPECIAL_TAGS: List[str] = Field(
        ["LASPH"], description="Special tags to prioritize for VASP Task Documents"
    )
    VASP_QUALITY_SCORES: Dict[str, int] = Field(
        {"SCAN": 3, "GGA+U": 2, "GGA": 1},
        description="Dictionary Mapping VASP calculation run types to rung level for VASP materials builders",
    )

    VASP_KPTS_TOLERANCE: float = Field(
        0.9,
        description="Relative tolerance for kpt density to still be a valid task document",
    )

    VASP_DEFAULT_INPUT_SETS: Dict = Field(
        {
            "GGA Structure Optimization": "pymatgen.io.vasp.sets.MPRelaxSet",
            "GGA+U Structure Optimization": "pymatgen.io.vasp.sets.MPRelaxSet",
        },
        description="Default input sets for task validation",
    )

    VASP_CHECKED_LDAU_FIELDS: List[str] = Field(
        ["LDAUU", "LDAUJ", "LDAUL"], description="LDAU fields to validate for tasks"
    )

    CP2K_SPECIAL_TAGS: List[str] = Field(
        [], description="Special tags to prioritize for CP2K task documents"
    )

    CP2K_QUALITY_SCORES: Dict[str, int] = Field(
        {"HYBRID": 4, "SCAN": 3, "GGA+U": 2, "GGA": 1},
        description="Dictionary Mapping CP2K calculation run types to rung level for CP2K materials builders",
    )

    CP2K_DEFAULT_INPUT_SETS: Dict = Field(
        {
            "GGA Structure Optimization": "pymatgen.io.cp2k.sets.RelaxSet",
            "GGA+U Structure Optimization": "pymatgen.io.cp2k.sets.RelaxSet",
        },
        description="Default input sets for task validation",
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

    @validator("VASP_DEFAULT_INPUT_SETS", pre=True)
    def load_input_sets(cls, values):
        input_sets = {}
        for name, inp_set in values.items():
            if isinstance(inp_set, str):
                _module = ".".join(inp_set.split(".")[:-1])
                _class = inp_set.split(".")[-1]
                input_sets[name] = getattr(importlib.import_module(_module), _class)
            elif isinstance(inp_set, type):
                input_sets[name] = inp_set

        return input_sets
