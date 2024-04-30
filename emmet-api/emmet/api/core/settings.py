from typing import Literal, Optional, List
from pydantic import Field
from emmet.api import __file__ as root_dir
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class MAPISettings(BaseSettings):
    """
    Special class to store settings for MAPI
    python module
    """

    DEBUG: bool = Field(False, description="Turns on debug mode for MAPI")

    TEST_FILES: str = Field(
        os.path.join(os.path.dirname(os.path.abspath(root_dir)), "../../../test_files"),
        description="Directory with test files",
    )

    DB_VERSION: str = Field("2021.11.10", description="Database version")

    DB_NAME_SUFFIX: Optional[Literal["blue", "green"]] = Field(
        None, description="Database name suffix. Either blue or green."
    )

    SORT_FIELDS: List[str] = Field(
        [
            "nsites",
            "nelements",
            "formula_pretty",
            "formula_anonymous",
            "chemsys",
            "volume",
            "density",
            "density_atomic",
            "material_id",
            "uncorrected_energy_per_atom",
            "energy_per_atom",
            "formation_energy_per_atom",
            "energy_above_hull",
            "band_gap",
            "cbm",
            "vbm",
            "efermi",
            "ordering",
            "total_magnetization",
            "total_magnetization_normalized_vol",
            "total_magnetization_normalized_formula_units",
            "num_magnetic_sites",
            "num_unique_magnetic_sites",
            "universal_anistropy",
            "homogeneous_poisson",
            "e_total",
            "e_ionic",
            "e_electronic",
            "n",
            "e_ij_max",
            "weighted_surface_energy_EV_PER_ANG2",
            "weighted_surface_energy",
            "weighted_work_function",
            "surface_anisotropy",
            "shape_factor",
        ],
        description="List of fields that support sorting",
    )
    TIMEOUT: int = Field(
        30,
        description="Number of seconds to wait for pymongo operations before raising a timeout error.",
    )
    model_config = SettingsConfigDict(env_prefix="MAPI_")
