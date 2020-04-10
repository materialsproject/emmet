"""
This file defines any arbitrary global variables used in Materials Project
database building and in the website code, to ensure consistency between
different modules and packages.
"""
import json
from pydantic import BaseSettings, Field, root_validator
from pydantic.types import Path

DEFAULT_CONFIG_FILE_PATH = str(Path.home().joinpath(".emmet.json"))


class EmmetSettings(BaseSettings):
    """
    Settings for the emmet- packages
    The default way to modify these is to modify ~/.emmet.json or set the environment variable
    EMMET_CONFIG_FILE to point to the json with emmet settings
    """

    config_file: Path = Field(
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

    class Config:
        env_prefix = "emmet_"
        extra = "ignore"

    @root_validator(pre=True)
    def load_default_settings(cls, values):
        """
        Loads settings from a root file if available and uses that as defaults in
        place of built in defaults
        """
        config_file_path = Path(values.get("config_file", DEFAULT_CONFIG_FILE_PATH))

        new_values = {}

        if config_file_path.exists():
            with open(config_file_path) as f:
                new_values = json.load(f)

        new_values.update(values)

        return new_values
