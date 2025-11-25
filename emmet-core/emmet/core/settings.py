"""Settings for defaults in the core definitions of Materials Project Documents."""

from __future__ import annotations

import gzip
import orjson
from pathlib import Path
from typing import TYPE_CHECKING

import requests  # type: ignore[import-untyped]
from monty.io import zopen
from monty.json import MontyDecoder
from pydantic import Field, ImportString, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self

DEFAULT_CONFIG_FILE_PATH = str(Path("~/.emmet.json").expanduser())


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

    QCHEM_FUNCTIONAL_QUALITY_SCORES: dict[str, int] = Field(
        {
            "wB97M-V": 7,
            "wB97X-V": 6,
            "wB97X-D3": 5,
            "wB97X-D": 5,
            "B3LYP": 4,
            "B97M-V": 3,
            "B97M-rV": 3,
            "B97-D3": 2,
            "B97-D": 2,
            "PBE": 1,
        },
        description="Dictionary mapping Q-Chem density functionals to a quality score.",
    )

    QCHEM_BASIS_QUALITY_SCORES: dict[str, int] = Field(
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

    QCHEM_SOLVENT_MODEL_QUALITY_SCORES: dict[str, int] = Field(
        {"CMIRS": 7, "SMD": 5, "ISOSVP": 4, "PCM": 3, "VACUUM": 1},
        description="Dictionary mapping Q-Chem solvent models to a quality score.",
    )

    QCHEM_TASK_QUALITY_SCORES: dict[str, int] = Field(
        {
            "single_point": 1,
            "geometry optimization": 2,
            "frequency-flattening geometry optimization": 3,
        },
        description="Dictionary mapping Q-Chem task type to a quality score",
    )

    VASP_STRUCTURE_QUALITY_SCORES: dict[str, int] = Field(
        {"r2SCAN": 5, "SCAN": 4, "GGA+U": 3, "GGA": 2, "PBEsol": 1},
        description="Dictionary Mapping VASP calculation run types to rung level for VASP materials builder structure data",  # noqa: E501
    )

    VASP_KPTS_TOLERANCE: float = Field(
        0.9,
        description="Relative tolerance for kpt density to still be a valid task document",
    )

    VASP_KSPACING_TOLERANCE: float = Field(
        0.05,
        description="Relative tolerance for kspacing to still be a valid task document",
    )

    VASP_MAX_MAGMOM: dict[str, float] = Field(
        {"Cr": 5}, description="Maximum permitted magnetic moments by element type."
    )

    VASP_DEFAULT_INPUT_SETS: dict[str, ImportString] = Field(
        {
            "GGA Structure Optimization": "pymatgen.io.vasp.sets.MPRelaxSet",
            "GGA+U Structure Optimization": "pymatgen.io.vasp.sets.MPRelaxSet",
            "r2SCAN Structure Optimization": "pymatgen.io.vasp.sets.MPScanRelaxSet",
            "SCAN Structure Optimization": "pymatgen.io.vasp.sets.MPScanRelaxSet",
            "PBEsol Structure Optimization": "pymatgen.io.vasp.sets.MPScanRelaxSet",
            "GGA Static": "pymatgen.io.vasp.sets.MPStaticSet",
            "GGA+U Static": "pymatgen.io.vasp.sets.MPStaticSet",
            "r2SCAN Static": "pymatgen.io.vasp.sets.MPScanStaticSet",
            "SCAN Static": "pymatgen.io.vasp.sets.MPScanStaticSet",
            "PBEsol Static": "pymatgen.io.vasp.sets.MPScanStaticSet",
            "HSE06 Static": "pymatgen.io.vasp.sets.MPScanStaticSet",
            "GGA NSCF Uniform": "pymatgen.io.vasp.sets.MPNonSCFSet",
            "GGA+U NSCF Uniform": "pymatgen.io.vasp.sets.MPNonSCFSet",
            "GGA NSCF Line": "pymatgen.io.vasp.sets.MPNonSCFSet",
            "GGA+U NSCF Line": "pymatgen.io.vasp.sets.MPNonSCFSet",
            "GGA NMR Electric Field Gradient": "pymatgen.io.vasp.sets.MPNMRSet",
            "GGA NMR Nuclear Shielding": "pymatgen.io.vasp.sets.MPNMRSet",
            "GGA+U NMR Electric Field Gradient": "pymatgen.io.vasp.sets.MPNMRSet",
            "GGA+U NMR Nuclear Shielding": "pymatgen.io.vasp.sets.MPNMRSet",
            "GGA Deformation": "pymatgen.io.vasp.sets.MPStaticSet",
            "GGA+U Deformation": "pymatgen.io.vasp.sets.MPStaticSet",
            "GGA DFPT Dielectric": "pymatgen.io.vasp.sets.MPStaticSet",
            "GGA+U DFPT Dielectric": "pymatgen.io.vasp.sets.MPStaticSet",
        },
        description="Default input sets for task validation",
    )

    VASP_VALIDATE_POTCAR_STATS: bool = Field(
        True, description="Whether to validate POTCAR stat values."
    )

    VASP_CHECKED_LDAU_FIELDS: list[str] = Field(
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

    USE_EMMET_MODELS: bool = Field(
        False,
        description=(
            "Whether to use emmet (True) or pymatgen (False, default) models "
            "for materials simulation outputs in certain document models "
            "which are used only in workflows and not in build pipelines."
        ),
    )

    model_config = SettingsConfigDict(env_prefix="emmet_", extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def load_default_settings(cls, values: Any) -> Any:
        """
        Loads settings from a root file if available and uses that as defaults in
        place of built in defaults
        """
        config_file_path: str = values.get("config_file", DEFAULT_CONFIG_FILE_PATH)

        new_values = {}

        # TODO: do we want to support gzipped config files?
        if config_file_path.startswith("http"):
            response = requests.get(config_file_path)
            if response.content.startswith(b"\x1f\x8b"):
                new_values = orjson.loads(gzip.decompress(response.content))
            else:
                new_values = orjson.loads(response.content)
        elif Path(config_file_path).exists():
            with zopen(config_file_path, "rb") as f:
                new_values = orjson.loads(f.read())

        new_values.update(values)

        return new_values

    @classmethod
    def autoload(cls, settings: None | dict | Self) -> Self:
        if settings is None:
            return cls(**{})
        elif isinstance(settings, dict):
            return cls(**settings)
        return settings

    @field_validator("VASP_DEFAULT_INPUT_SETS", mode="before")
    @classmethod
    def convert_input_sets(cls, value):
        if isinstance(value, dict):
            return {k: MontyDecoder().process_decoded(v) for k, v in value.items()}
        return value

    def as_dict(self):
        """
        HotPatch to enable serializing EmmetSettings via Monty
        """
        return self.model_dump(exclude_unset=True, exclude_defaults=True)
