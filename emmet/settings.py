"""
This file defines any arbitrary global variables used in Materials Project
database building and in the website code, to ensure consistency between
different modules and packages.
"""
import json
from pydantic import BaseSettings, Field, root_validator
from pydantic.types import Path


class EmmetSettings(BaseSettings):

    config_file: Path = Field(
        "~/.emmet.json", description="File to load alternative defaults from"
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

    class Config:
        env_prefix = "emmet_"

    @root_validator(pre=True)
    def load_default_settings(cls, values):
        """
        Loads settings from a root file if available and uses that as defaults in
        place of built in defaults
        """
        config_file_path = Path(values.get("config_file", "~/.emmet.json"))

        new_values = {}

        if config_file_path.exists():
            with open(config_file_path) as f:
                new_values = json.load(f)

        new_values.update(values)

        return new_values


SETTINGS = EmmetSettings()
