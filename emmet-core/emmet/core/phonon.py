"""Define schemas for DFPT, phonopy, and pheasy-derived phonon data."""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
import yaml  # type: ignore[import-untyped]
from monty.dev import requires
from monty.io import zopen
from monty.os.path import zpath
from pydantic import BaseModel, Field, PrivateAttr, computed_field, model_validator
from pymatgen.core import Lattice, Structure
from pymatgen.electronic_structure.bandstructure import Kpoint
from pymatgen.phonon.bandstructure import PhononBandStructureSymmLine
from pymatgen.phonon.dos import PhononDos as PhononDosObject
from typing_extensions import Literal

from emmet.core import ARROW_COMPATIBLE
from emmet.core.base import CalcMeta
from emmet.core.common import convert_datetime
from emmet.core.math import Matrix3D, Tensor4R, Vector3D
from emmet.core.mpid import MPID
from emmet.core.polar import BornEffectiveCharges, DielectricDoc, IRDielectric
from emmet.core.structure import StructureMetadata
from emmet.core.typing import PhononWebsiteDict, TypedAbinitInputVars
from emmet.core.utils import DocEnum, get_num_formula_units, utcnow

try:
    import pyarrow as pa
    from pyarrow import Table as ArrowTable
except ImportError:
    pa = None
    ArrowTable = None

if ARROW_COMPATIBLE:
    import emmet.core.serialization_adapters.phonon_adapter

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from typing_extensions import Self

DEFAULT_PHONON_FILES = {
    "structure": "POSCAR",
    "phonon_bandstructure": "band.yaml",  # chosen as Phonopy default
    "phonon_dos": "total_dos.dat",  # chosen as Phonopy default
    "force_constants": "FORCE_CONSTANTS",  # chosen as Phonopy default
    "born": "born.npz",
    "epsilon_static": "epsilon_static.npz",
    "phonopy_output": "phonopy.yaml",
}


class PhononMethod(Enum):
    """Define common methods for computed phonon properties."""

    DFPT = "dfpt"
    PHONOPY = "phonopy"
    PHEASY = "pheasy"


class PhononDOS(BaseModel):
    """Define schema of pymatgen phonon density of states."""

    frequencies: list[float] = Field(description="The phonon frequencies in THz.")
    densities: list[float] = Field(description="The phonon density of states.")

    @cached_property
    def to_pmg(self) -> PhononDosObject:
        """Get / cache corresponding pymatgen object."""
        return PhononDosObject(frequencies=self.frequencies, densities=self.densities)

    @requires(pa is not None, "`pip install pyarrow` to use this functionality.")
    def to_arrow(self, col_prefix: str | None = None) -> ArrowTable:
        """Convert PhononDOS to a pyarrow Table."""
        col_prefix = col_prefix or ""
        return pa.Table.from_pydict(
            {
                f"{col_prefix}{k}": [getattr(self, k)]
                for k in ("frequencies", "densities")
            }
        )

    @classmethod
    @requires(pa is not None, "`pip install pyarrow` to use this functionality.")
    def from_arrow(cls, table: ArrowTable, col_prefix: str | None = None) -> Self:
        """Create a PhononDOS from a pyarrow Table."""
        col_prefix = col_prefix or ""
        return cls(
            **{k: table[f"{col_prefix}{k}"].to_pylist()[0] for k in cls.model_fields}
        )

    @classmethod
    def from_phonopy(cls, phonon_dos_file: str | Path) -> Self:
        """Create a PhononDOS from phonopy .dat output."""
        phonopy_dos: dict[str, list[float]] = {
            k: []
            for k in (
                "frequencies",
                "densities",
            )
        }
        with zopen(phonon_dos_file, "rt") as f:
            for line in f.read().splitlines():
                non_comment_text = line.split("#")[0]  # type: ignore[arg-type]
                if len(cols := non_comment_text.split()) == 2:
                    phonopy_dos["frequencies"].append(float(cols[0]))
                    phonopy_dos["densities"].append(float(cols[1]))

        return cls(**phonopy_dos)


class PhononBS(BaseModel):
    """Define schema of pymatgen phonon band structure."""

    qpoints: list[Vector3D] = Field(
        description="The q-kpoints at which the band structure was sampled, in direct coordinates.",
    )
    frequencies: list[list[float]] = Field(
        description="The phonon frequencies in THz, with the first index representing the band, and the second the q-point.",
    )
    reciprocal_lattice: Matrix3D = Field(description="The reciprocal lattice.")
    has_nac: bool = Field(
        False,
        description="Whether the calculation includes non-analytical corrections at Gamma.",
    )
    eigendisplacements: list[
        list[list[tuple[complex, complex, complex]]]
    ] | None = Field(
        None, description="Phonon eigendisplacements in Cartesian coordinates."
    )
    labels_dict: dict[str, Vector3D] | None = Field(
        None, description="The high-symmetry labels of specific q-points."
    )
    structure: Structure | None = Field(
        None, description="The structure associated with the calculation."
    )
    _primitive_structure: Structure | None = PrivateAttr(None)

    @model_validator(mode="before")
    def rehydrate(cls, config: Any) -> Any:
        """Ensure fields are correctly populated."""
        if isinstance(egd := config.get("eigendisplacements"), dict) and all(
            egd.get(k) is not None for k in ("real", "imag")
        ):
            config["eigendisplacements"] = (
                np.array(egd["real"]) + 1j * np.array(egd["imag"])
            ).tolist()

        if (struct := config.get("structure")) and not isinstance(struct, Structure):
            config["structure"] = Structure.from_dict(struct)

        # remap legacy fields
        for k, v in {
            "lattice_rec": "reciprocal_lattice",
            "bands": "frequencies",
        }.items():
            if config.get(k):
                config[v] = config.pop(k)

        if isinstance(config["reciprocal_lattice"], dict):
            config["reciprocal_lattice"] = config["reciprocal_lattice"].get("matrix")

        return config

    @property
    def primitive_structure(self) -> Structure | None:
        """Cache primitive structure for use in computing entropy, heat capacity, etc."""
        if self.structure and not self._primitive_structure:
            self._primitive_structure = self.structure.get_primitive_structure()
        return self._primitive_structure

    @cached_property
    def to_pmg(self) -> PhononBandStructureSymmLine:
        """Get / cache corresponding pymatgen object."""
        rlatt = Lattice(self.reciprocal_lattice)
        return PhononBandStructureSymmLine(
            [Kpoint(q, lattice=rlatt).frac_coords for q in self.qpoints],  # type: ignore[misc]
            np.array(self.frequencies),
            rlatt,
            has_nac=self.has_nac,
            eigendisplacements=np.array(self.eigendisplacements),
            structure=self.structure,
            labels_dict={
                k: Kpoint(v, lattice=rlatt).frac_coords
                for k, v in (self.labels_dict or {}).items()
            },
            coords_are_cartesian=False,
        )

    @requires(pa is not None, "`pip install pyarrow` to use this functionality.")
    def to_arrow(self, col_prefix: str | None = None) -> ArrowTable:
        """Convert a PhononBS to an arrow table."""
        config = self.model_dump()
        if structure := config.pop("structure", None):
            config["structure"] = json.dumps(structure.as_dict())

        for k in ("qpoints", "frequencies", "reciprocal_lattice", "eigendisplacements"):
            if (vals := config.pop(k, None)) and k == "eigendisplacements":
                cvals = np.array(vals)
                config["eigendisplacements_real"] = cvals.real.tolist()
                config["eigendisplacements_imag"] = cvals.imag.tolist()
            elif vals:
                rvals = np.array(vals)
                config[k] = rvals.tolist()

        if qpt_labels := config.pop("labels_dict"):
            config["qpoint_labels"] = list(qpt_labels)
            config["qpoint_labelled_points"] = [
                qpt_labels[k] for k in config["qpoint_labels"]
            ]

        col_prefix = col_prefix or ""
        return pa.Table.from_pydict(
            {f"{col_prefix}{k}": [v] for k, v in config.items()}
        )

    @classmethod
    @requires(pa is not None, "`pip install pyarrow` to use this functionality.")
    def from_arrow(cls, table: ArrowTable, col_prefix: str | None = None) -> Self:
        """Create a PhononBS from an arrow table."""
        col_prefix = col_prefix or ""
        config: dict[str, Any] = {}
        for k in (
            "structure",
            "has_nac",
            "qpoints",
            "frequencies",
            "reciprocal_lattice",
            "eigendisplacements_real",
            "qpoint_labels",
        ):
            _k = f"{col_prefix}{k}"
            if _k not in table.column_names:
                continue
            v = table[_k].to_pylist()[0]
            if k == "structure":
                config[k] = Structure.from_dict(json.loads(v))
            elif k in ("qpoints", "frequencies", "reciprocal_lattice"):
                config[k] = np.array(v)
            elif k == "eigendisplacements_real":
                config["eigendisplacements"] = (
                    table[f"{col_prefix}eigendisplacements_real"].to_numpy()[0]
                    + 1.0j * table[f"{col_prefix}eigendisplacements_imag"].to_numpy()[0]
                )
            elif k == "qpoint_labels":
                config["labels_dict"] = dict(
                    zip(v, table[f"{col_prefix}qpoint_labelled_points"].to_pylist()[0])
                )
            else:
                config[k] = v
        return cls(**config)

    @classmethod
    def from_phonopy(cls, phonon_bandstructure_file: str | Path):
        """Create a PhononBS from phonopy .yaml output."""
        with zopen(phonon_bandstructure_file, "rt") as f:
            phonopy_bandstructure = yaml.safe_load(f.read())

        phonopy_bandstructure.update(
            qpoints=[entry["q-position"] for entry in phonopy_bandstructure["phonon"]],
            frequencies=[
                [branch["frequency"] for branch in entry["band"]]
                for entry in phonopy_bandstructure["phonon"]
            ],
        )
        return cls(**phonopy_bandstructure)


class SumRuleChecks(BaseModel):
    """Container class for defining sum rule checks."""

    asr: float | None = Field(
        None, description="The violation of the acoustic sum rule."
    )
    cnsr: float | None = Field(
        None, description="The violation of the charge neutral sum rule."
    )


class PhononComputationalSettings(BaseModel):
    """Collection to store computational settings for the phonon computation."""

    # could be optional and implemented at a later stage?
    npoints_band: int | None = Field(
        None, description="number of points for band structure computation"
    )
    kpath_scheme: str | None = Field(None, description="indicates the kpath scheme")
    kpoint_density_dos: int | None = Field(
        None,
        description="number of points for computation of free energies and densities of states",
    )


class ThermalDisplacementData(BaseModel):
    """Collection to store information on the thermal displacement matrices."""

    freq_min_thermal_displacements: float | None = Field(
        None,
        description="cutoff frequency in THz to avoid numerical issues in the "
        "computation of the thermal displacement parameters",
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


class PhononBSDOSTask(StructureMetadata):
    """Phonon band structures and density of states data."""

    identifier: str | None = Field(
        None, description="The identifier of this phonon analysis task."
    )

    phonon_method: PhononMethod | None = Field(
        None, description="The method used to calculate phonon properties."
    )

    phonon_bandstructure: PhononBS | None = Field(
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
        None,
        description="The electronic contribution to the high-frequency dielectric constant.",
    )

    born: list[Matrix3D] | None = Field(
        None,
        description="Born charges, only for symmetrically inequivalent atoms",
    )

    # needed, e.g. to compute Grueneisen parameter etc
    force_constants: list[list[Matrix3D]] | None = Field(
        None, description="Force constants between every pair of atoms in the structure"
    )

    last_updated: datetime = Field(
        default_factory=utcnow,
        description="Timestamp for the most recent calculation for this Material document.",
    )

    sum_rules_breaking: SumRuleChecks | None = Field(
        None,
        description="Deviations from sum rules.",
    )

    structure: Structure | None = Field(
        None, description="Structure used in the calculation."
    )

    total_dft_energy: float | None = Field(
        None, description="total DFT energy in eV/atom."
    )

    volume_per_formula_unit: float | None = Field(
        None, description="volume per formula unit in Angstrom**3."
    )

    formula_units: int | None = Field(None, description="Formula units per cell.")

    supercell_matrix: Matrix3D | None = Field(
        None, description="matrix describing the supercell."
    )
    primitive_matrix: Matrix3D | None = Field(
        None, description="matrix describing relationship to primitive cell."
    )

    code: str | None = Field(
        None, description="String describing the code for the computation."
    )

    post_process_settings: PhononComputationalSettings | None = Field(
        None,
        description="Field including settings for the post processing code, e.g., phonopy.",
    )

    thermal_displacement_data: ThermalDisplacementData | None = Field(
        None,
        description="Includes all data of the computation of the thermal displacements",
    )

    calc_meta: list[CalcMeta] | None = Field(
        None,
        description="Metadata for individual calculations used to build this document.",
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_fields(cls, config: Any) -> Any:
        """Migrate legacy input fields."""

        # This block is for older DFPT data
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

        if (ph_bs := config.get("phonon_bandstructure")) and not config.get(
            "structure"
        ):
            if isinstance(ph_bs, PhononBandStructureSymmLine | PhononBS):
                config["structure"] = ph_bs.structure
            else:
                config["structure"] = ph_bs.get("structure")

        # This block is for the migration from atomate2 --> emmet-core schemas
        if config.get("structure"):
            if isinstance(config["structure"], dict):
                config["structure"] = Structure.from_dict(config["structure"])

            old_formula_units = config.pop("formula_units", 1)
            if toten := config.pop("total_dft_energy", None):
                config["total_energy"] = (
                    toten * old_formula_units / config["structure"].num_sites
                )

            config["formula_units"] = get_num_formula_units(
                config["structure"].composition
            )

        if (fc := config.get("force_constants")) and isinstance(fc, dict):
            config["force_constants"] = fc["force_constants"]

        if comp_sett := config.get("phonopy_settings"):
            config["post_process_settings"] = comp_sett

        calc_meta_migrate = {
            "uuids": "_uuid",
            "jobdirs": "_job_dir",
        }
        calc_meta_remap = {"uuids": "identifier", "jobdirs": "dir_name"}
        if any(config.get(k) for k in calc_meta_migrate):
            calc_meta: dict[str, dict[str, str]] = {}
            for field_name, splitter in calc_meta_migrate.items():
                if vals := config.get(field_name):
                    if not isinstance(vals, dict):
                        vals = vals.model_dump()
                    for k, v in vals.items():
                        job_name = k.split(splitter)[0]
                        if isinstance(v, list):
                            for idx, sub_v in enumerate(v):
                                if (sub_name := f"{job_name}-{idx}") not in calc_meta:
                                    calc_meta[sub_name] = {}
                                calc_meta[sub_name][calc_meta_remap[field_name]] = sub_v
                        else:
                            if job_name not in calc_meta:
                                calc_meta[job_name] = {}
                            calc_meta[job_name][calc_meta_remap[field_name]] = v

            config["calc_meta"] = [
                CalcMeta(
                    name=job_name,
                    **meta,
                )
                for job_name, meta in calc_meta.items()
            ]

        return config

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def has_imaginary_modes(self) -> bool | None:
        tol: float = 1e-5
        if self.phonon_bandstructure:
            return self.phonon_bandstructure.to_pmg.has_imaginary_freq(tol=tol)
        elif self.phonon_dos:
            return bool(
                np.any(
                    np.array(self.phonon_dos.densities)[
                        np.array(self.phonon_dos.frequencies) < tol
                    ]
                    > tol
                )
            )
        return None

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def charge_neutral_sum_rule(self) -> Matrix3D | None:
        """Sum of Born effective charges over sites should be zero."""
        if self.born:
            bec = np.array(self.born)
            return tuple(tuple(row) for row in np.sum(bec, axis=0).tolist())
        return None

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def acoustic_sum_rule(self) -> Matrix3D | None:
        """Sum of q=0 atomic force constants should be zero."""
        if self.force_constants:
            return tuple(
                tuple(row)
                for row in np.einsum("iijk->jk", np.array(self.force_constants))
            )
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def check_sum_rule_deviations(self) -> SumRuleChecks:
        """Report deviations from sum rules."""
        if not self.sum_rules_breaking:
            self.sum_rules_breaking = SumRuleChecks(
                **{
                    k: (
                        np.max(np.abs(getattr(self, attr)))
                        if getattr(self, attr)
                        else None
                    )
                    for k, attr in {
                        "asr": "acoustic_sum_rule",
                        "cnsr": "charge_neutral_sum_rule",
                    }.items()
                }
            )
        return self.sum_rules_breaking

    def _get_thermo_from_dos(
        self,
        quantity: Literal["entropy", "cv", "internal_energy", "helmholtz_free_energy"],
        temperature: float,
        normalization: Literal["atoms", "formula_units"] | None = "formula_units",
    ) -> float | None:
        """Get a thermodynamic property from the phonon DOS.

        quantity : "entropy", "cv", "internal_energy", or "helmholtz_free_energy"
            If "entropy" or "cv", the units before normalization are J/(K * mol).
            If "internal_energy" or "helmholtz_free_energy", the units before normalization are J/mol.
        temperature : float
        normalization : "atoms", "formula_units", or None
            Whether to normalize by the number of atoms in the cell ("atoms"),
            the number of formula units ("formula_units", default), or not (None).
        """

        if not self.phonon_dos:
            return None

        if normalization and not self.structure:
            raise ValueError(
                "Cannot normalize thermodynamic quantities without a structure."
            )

        norm_fac = 1.0
        if normalization == "atoms":
            norm_fac = 1.0 / self.structure.num_sites  # type: ignore[union-attr]
        elif normalization == "formula_units":
            norm_fac = 1.0 / self.formula_units  # type: ignore[operator]
        else:
            raise ValueError(f"Unknown {normalization=} convention.")

        return (
            getattr(self.phonon_dos.to_pmg, quantity)(
                temp=temperature,
            )
            * norm_fac
        )

    def entropy(
        self,
        temperature: float,
        normalization: Literal["atoms", "formula_units"] | None = "formula_units",
    ) -> float | None:
        """Compute the entropy in J/(K * mol * formula units).

        temperature : float
        normalization : "atoms", "formula_units", or None
            Whether to normalize by the number of atoms in the cell ("atoms"),
            the number of formula units ("formula_units"), or not (None).
        """
        return self._get_thermo_from_dos(
            "entropy", temperature, normalization=normalization
        )

    def heat_capacity(
        self,
        temperature: float,
        normalization: Literal["atoms", "formula_units"] | None = "formula_units",
    ) -> float | None:
        """Compute the heat capacity in J/(K * mol * formula units).

        temperature : float
        normalization : "atoms", "formula_units", or None
            Whether to normalize by the number of atoms in the cell ("atoms"),
            the number of formula units ("formula_units"), or not (None).
        """
        return self._get_thermo_from_dos("cv", temperature, normalization=normalization)

    def internal_energy(
        self,
        temperature: float,
        normalization: Literal["atoms", "formula_units"] | None = "formula_units",
    ) -> float | None:
        """Compute the internal energy in J/(mol * formula units).

        temperature : float
        normalization : "atoms", "formula_units", or None
            Whether to normalize by the number of atoms in the cell ("atoms"),
            the number of formula units ("formula_units"), or not (None).
        """
        return self._get_thermo_from_dos(
            "internal_energy", temperature, normalization=normalization
        )

    def free_energy(
        self,
        temperature: float,
        normalization: Literal["atoms", "formula_units"] | None = "formula_units",
    ) -> float | None:
        """Compute the Helmholtz free energy in J/(mol * formula units).

        temperature : float
        normalization : "atoms", "formula_units", or None
            Whether to normalize by the number of atoms in the cell ("atoms"),
            the number of formula units ("formula_units"), or not (None).
        """
        return self._get_thermo_from_dos(
            "helmholtz_free_energy", temperature, normalization=normalization
        )

    def compute_thermo_quantites(
        self,
        temperatures: Sequence[float],
        normalization: Literal["atoms", "formula_units"] | None = "formula_units",
    ) -> dict[str, Sequence[float | None]]:
        """Compute all thermodynamic quantities as a convenience method."""

        quantities = {
            "entropy": "entropy",
            "heat_capacity": "cv",
            "internal_energy": "internal_energy",
            "free_energy": "helmholtz_free_energy",
        }

        thermo_props: dict[str, Sequence[float | None]] = {
            k: [
                self._get_thermo_from_dos(v, temp, normalization=normalization)  # type: ignore[arg-type]
                for temp in temperatures
            ]
            for k, v in quantities.items()
        }
        thermo_props["temperature"] = temperatures
        return thermo_props

    @requires(pa is not None, "`pip install pyarrow` to use this functionality.")
    def objects_to_arrow(self) -> ArrowTable:
        """Convert band structure and DOS to pyarrow table row."""
        table = pa.Table.from_pydict({"material_id": [self.material_id]})
        if self.phonon_bandstructure:
            bst = self.phonon_bandstructure.to_arrow(col_prefix="bs_")
            for k in bst.column_names:
                table = table.append_column(k, bst[k])

        if self.phonon_dos:
            dost = self.phonon_dos.to_arrow(col_prefix="dos_")

            for k in dost.column_names:
                table = table.append_column(k, dost[k])
        return table

    @classmethod
    def from_phonopy_pheasy_files(
        cls,
        structure_file: str | Path,
        phonon_bandstructure_file: str | Path | None = None,
        phonon_dos_file: str | Path | None = None,
        force_constants_file: str | Path | None = None,
        born_file: str | Path | None = None,
        epsilon_static_file: str | Path | None = None,
        phonopy_output_file: str | Path | None = None,
        **kwargs,
    ) -> Self:
        """
        Create a PhononBSDOSDoc from a list of explicit Phonopy/Pheasy file paths.
        """

        cls_config: dict[str, Any] = {
            "structure": Structure.from_file(structure_file),
        }
        if "poscar" in str(structure_file).lower():
            cls_config["code"] = "vasp"

        if phonon_bandstructure_file:
            cls_config["phonon_bandstructure"] = PhononBS.from_phonopy(
                phonon_bandstructure_file
            )

        if phonon_dos_file:
            cls_config["phonon_dos"] = PhononDOS.from_phonopy(phonon_dos_file)

        if force_constants_file:
            # read FORCE_CONSTANTS manually
            force_constant_matrix: np.ndarray
            idxs: tuple[int | None, int | None] = (
                None,
                None,
            )
            irow = 0
            with zopen(force_constants_file, "rt") as f:
                for idx, line in enumerate(f.read().splitlines()):
                    vals = line.strip().split()
                    if idx == 0:
                        force_constant_matrix = np.zeros(
                            (int(vals[0]), int(vals[1]), 3, 3)
                        )
                    elif len(vals) == 2:
                        # idxs written like this for mypy
                        idxs = (
                            int(vals[0]) - 1,
                            int(vals[1]) - 1,
                        )
                        irow = 0
                    elif len(vals) == 3:
                        force_constant_matrix[idxs[0], idxs[1], irow] = [
                            float(v) for v in vals
                        ]
                        irow += 1
            cls_config["force_constants"] = force_constant_matrix.tolist()

        if born_file:
            cls_config["born"] = np.load(born_file)
        if epsilon_static_file:
            cls_config["epsilon_static"] = np.load(epsilon_static_file)

        if phonopy_output_file:
            with zopen(phonopy_output_file, "rt") as f:
                phonopy_output = yaml.safe_load(f.read())
            for k in ("primitive_matrix", "supercell_matrix"):
                cls_config[k] = phonopy_output.get(k)

        return cls.from_structure(cls_config["structure"], **cls_config, **kwargs)

    @classmethod
    def from_phonopy_pheasy_directory(
        cls,
        phonon_dir: Path | str,
        **kwargs,
    ) -> Self:
        """Create a PhononBSDOSDoc from a Phonopy/Pheasy directory.

        Parameters
        -----------
        phonon_dir : str or Path
        **kwargs to pass to `PhononBSDOSDoc.from_phonopy_pheasy_files`
        """
        phonon_path = Path(phonon_dir).resolve()
        file_paths = {}
        for k, file_name in DEFAULT_PHONON_FILES.items():
            if (file_path := Path(zpath(str(phonon_path / file_name)))).exists():
                file_paths[f"{k}_file"] = file_path
        return cls.from_phonopy_pheasy_files(**file_paths, **kwargs)


class PhononBSDOSDoc(PhononBSDOSTask):
    """Built data version of PhononBSDOSTask."""

    material_id: MPID | None = Field(
        None,
        description="The Materials Project ID of the material, of the form mp-******.",
    )
    task_ids: list[str] | None = Field(
        None, description="A list of identifiers that were used to build this document."
    )

    @model_validator(mode="after")
    def match_id_fields(self) -> Self:
        """Ensure that `material_id` aliases inherited `identifier` field."""
        self.identifier = self.material_id
        return self


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

    ddb: str | None = Field(None, description="The string of the DDB file.")

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
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=utcnow,
    )


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

    mode_types: list[tuple[Optional[str], Optional[str], Optional[str]]] = Field(
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
