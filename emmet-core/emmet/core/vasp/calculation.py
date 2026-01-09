"""Core definitions of a VASP calculation documents."""

from __future__ import annotations

from copy import deepcopy
from functools import cached_property
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Annotated, Type

import numpy as np
import orjson
from monty.io import zopen
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
    BeforeValidator,
)
from pymatgen.command_line.bader_caller import bader_analysis_from_path
from pymatgen.command_line.chargemol_caller import ChargemolAnalysis
from pymatgen.core.structure import Structure
from pymatgen.electronic_structure.core import OrbitalType
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.io.vasp import BSVasprun, Kpoints, Locpot, Oszicar, Outcar, Poscar
from pymatgen.io.vasp import Potcar as VaspPotcar
from pymatgen.io.vasp import PotcarSingle, Vasprun, VolumetricData
from typing_extensions import NotRequired, TypedDict

from emmet.core.band_theory import ElectronicBS, ElectronicDos
from emmet.core.math import ListMatrix3D, Matrix3D, Vector3D
from emmet.core.trajectory import RelaxTrajectory, Trajectory
from emmet.core.vasp.models import ElectronicStep, ChgcarLike
from emmet.core.types.enums import StoreTrajectoryOption, TaskState, VaspObject
from emmet.core.types.pymatgen_types.bader import BaderAnalysis
from emmet.core.types.pymatgen_types.kpoints_adapter import KpointsType
from emmet.core.types.pymatgen_types.lattice_adapter import LatticeType
from emmet.core.types.pymatgen_types.outcar_adapter import OutcarType
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.typing import JsonDictType, _dict_items_zipper
from emmet.core.utils import type_override
from emmet.core.vasp.calc_types import (
    CalcType,
    RunType,
    TaskType,
    calc_type,
    run_type,
    task_type,
)

from emmet.core.settings import EmmetSettings

SETTINGS = EmmetSettings()

if TYPE_CHECKING:
    from typing_extensions import Self
    from pymatgen.electronic_structure.bandstructure import BandStructure
    from pymatgen.electronic_structure.dos import CompleteDos


logger = logging.getLogger(__name__)


class Potcar(BaseModel):
    pot_type: str | None = Field(None, description="Pseudo-potential type, e.g. PAW")
    functional: str | None = Field(
        None, description="Functional type use in the calculation."
    )
    symbols: list[str] | None = Field(
        None, description="List of VASP potcar symbols used in the calculation."
    )


class CalculationBaseModel(BaseModel):
    """Wrapper around pydantic BaseModel with extra functionality."""

    def get(self, key: Any, default_value: Any | None = None) -> Any:
        return getattr(self, key, default_value)


class TypedStatisticsDict(TypedDict):
    MEAN: float
    ABSMEAN: float
    VAR: float
    MIN: float
    MAX: float


class TypedPotcarKeywordsDict(TypedDict):
    header: list[str]
    data: list[str]


class TypedPotcarStatsDict(TypedDict):
    header: TypedStatisticsDict
    data: TypedStatisticsDict


class TypedPotcarSummaryStatsDict(TypedDict):
    keywords: NotRequired[TypedPotcarKeywordsDict | None]
    stats: NotRequired[TypedPotcarStatsDict | None]


class PotcarSpec(BaseModel):
    """Document defining a VASP POTCAR specification."""

    titel: str | None = Field(None, description="TITEL field from POTCAR header")
    hash: str | None = Field(None, description="md5 hash of POTCAR file")
    summary_stats: TypedPotcarSummaryStatsDict | None = Field(
        None,
        description="summary statistics used to ID POTCARs without hashing",
    )

    @classmethod
    def from_potcar_single(cls, potcar_single: PotcarSingle) -> Self:
        """
        Get a PotcarSpec from a PotcarSingle.

        Parameters
        ----------
        potcar_single
            A potcar single object.

        Returns
        -------
        PotcarSpec
            A potcar spec.
        """
        return cls(
            titel=potcar_single.TITEL,
            hash=potcar_single.md5_header_hash,
            summary_stats=potcar_single._summary_stats,  # type: ignore[arg-type]
        )

    @classmethod
    def from_potcar(cls, potcar: VaspPotcar) -> list["PotcarSpec"]:
        """
        Get a list of PotcarSpecs from a Potcar.

        Parameters
        ----------
        potcar
            A potcar object.

        Returns
        -------
        list[PotcarSpec]
            A list of potcar specs.
        """
        return [cls.from_potcar_single(p) for p in potcar]

    @classmethod
    def from_file(cls, file_path: str | Path) -> list["PotcarSpec"]:
        """
        Get a list of PotcarSpecs from a Potcar.

        Parameters
        ----------
        file_path : str or Path of the POTCAR

        Returns
        -------
        list[PotcarSpec]
            A list of potcar specs.
        """
        if ".spec" in str(file_path):
            with zopen(file_path, "rt") as psf:
                try:
                    # POTCAR spec is a model-dumped list of PotcarSpec
                    return [cls(**ps) for ps in orjson.loads(psf.read())]
                except orjson.JSONDecodeError:
                    # POTCAR spec is a pymatgen-style newline-delimited list of symbols
                    return [cls(titel=symb) for symb in psf.read().splitlines()]  # type: ignore[arg-type,call-arg]
        return cls.from_potcar(VaspPotcar.from_file(str(file_path)))


@type_override({"incar": str, "parameters": str})
class CalculationInput(CalculationBaseModel):
    """Document defining VASP calculation inputs.

    Note that the following fields were formerly top-level fields on InputDoc,
    but are now properties of `CalculationInput`:
        pseudo_potentials (Potcar) : summary of the POTCARs used in the calculation
        xc_override (str) : the exchange-correlation functional used if not
            the one specified by POTCAR
        is_lasph (bool) : how the calculation set LASPH (aspherical corrections)
        magnetic_moments (list of floats) : on-site magnetic moments
    """

    incar: JsonDictType = Field(
        None, description="INCAR parameters for the calculation"
    )
    kpoints: KpointsType | None = Field(None, description="KPOINTS for the calculation")
    nkpoints: int | None = Field(None, description="Total number of k-points")
    potcar_spec: list[PotcarSpec] | None = Field(
        None, description="Title and hash of POTCAR files used in the calculation"
    )
    potcar: list[str] | None = Field(
        None, description="The symbols of the POTCARs used in the calculation."
    )
    potcar_type: list[str] | None = Field(
        None, description="List of POTCAR functional types."
    )
    parameters: JsonDictType = Field(None, description="Parameters from vasprun")
    lattice_rec: LatticeType | None = Field(
        None, description="Reciprocal lattice of the structure"
    )
    structure: StructureType | None = Field(
        None, description="Input structure for the calculation"
    )
    is_hubbard: bool = Field(
        default=False, description="Is this a Hubbard +U calculation"
    )
    hubbards: Annotated[
        dict[str, float] | None, BeforeValidator(_dict_items_zipper)
    ] = Field(None, description="The hubbard parameters used")

    @model_validator(mode="before")
    @classmethod
    def clean_inputs(cls, config: Any) -> Any:
        """Ensure whitespace in parameters and Kpoints are serialized.

        NOTE:
        ------
        A change in VASP introduced whitespace into some parameters,
        for example `<i type="string" name="GGA    ">PE</I>` was observed in
        VASP 6.4.3. This will lead to an incorrect return value from RunType.
        This validator will ensure that any already-parsed documents are fixed.
        """
        if (kpts := config.get("kpoints")) and isinstance(kpts, dict):
            config["kpoints"] = Kpoints.from_dict(kpts)

        # Issue: older tasks don't always contain `input.potcar`
        # and `input.potcar_spec`
        # Newer tasks contain `input.potcar`, `input.potcar_spec`,
        # and `orig_inputs.potcar_spec`

        # orig_inputs.potcar used to be what is now potcar_spec
        # try to coerce back here, but not guaranteed
        if (pcar := config.get("potcar")) and not config.get("potcar_spec"):
            if isinstance(pcar, dict):
                if pcar.get("@class") == "Potcar":
                    try:
                        # If POTCAR library is available
                        pcar = VaspPotcar.from_dict(pcar)
                    except ValueError:
                        # No POTCAR library available
                        config["potcar"] = pcar.get("symbols")
                        config["potcar_type"] = [pcar.get("functional")]
                else:
                    pcar = Potcar(**pcar)

            if isinstance(pcar, VaspPotcar):
                config["potcar_spec"] = PotcarSpec.from_potcar(pcar)
                config.pop("potcar")
            elif isinstance(pcar, Potcar):
                config["potcar_type"] = [pcar.pot_type] if pcar.pot_type else None
                config["potcar"] = pcar.symbols
            else:
                try:
                    pspec = [PotcarSpec(**x) for x in pcar]
                    config["potcar_spec"] = pspec
                    config.pop("potcar")
                except Exception:
                    if not isinstance(pcar, list) or not all(
                        isinstance(x, str) for x in pcar
                    ):
                        config.pop("potcar")

        if (pspec := config.get("potcar_spec")) and config.get("potcar") is None:
            config["potcar"] = []
            for spec in pspec:
                if isinstance(spec, PotcarSpec) and spec.titel:
                    titel = spec.titel
                elif isinstance(spec, dict) and spec.get("titel"):
                    titel = spec["titel"]
                else:
                    continue
                symbs = titel.split()
                if len(symbs) >= 2:
                    symb = symbs[1]
                else:
                    symb = symbs[0]
                config["potcar"].append(symb)

        return config

    def model_post_init(self, context: Any, /) -> None:
        # populate legacy hubbards data
        if (
            (
                self.is_hubbard
                or (self.incar or {}).get("LDAU")
                or (self.parameters or {}).get("LDAU")
            )
            and not self.hubbards
            and self.potcar
        ):
            # Basically the same functionality as in pymatgen Vasprun
            symbols = [symb.split("_", 1)[0] for symb in self.potcar]

            input_params = {
                k: v
                for inc_k in (
                    "incar",
                    "parameters",
                )
                for k, v in (getattr(self, inc_k) or {}).items()
            }
            u = input_params.get("LDAUU", [])
            j = input_params.get("LDAUJ", [])
            if len(j) != len(u):
                j = [0] * len(u)
            if len(u) == len(symbols):
                self.hubbards = {
                    symbols[idx]: u[idx] - j[idx] for idx in range(len(symbols))
                }

    @cached_property
    def poscar(self) -> Poscar | None:
        """Return pymatgen object representing the POSCAR file."""
        if self.structure:
            return Poscar(self.structure)
        return None

    @property
    def is_lasph(self) -> bool | None:
        """Report if the calculation was run with aspherical corrections.

        If `self.parameters` is populated, returns the value of `LASPH`
        from vasprun.xml, or its default value if not set (`False`).

        If `self.parameters` isn't populated (vasprun.xml wasn't parsed),
        returns `None`.
        """
        if self.parameters:
            return self.parameters.get("LASPH", False)
        return None

    @property
    def pseudo_potentials(self) -> Potcar | None:
        """Summarize the pseudo-potentials used."""
        if not self.potcar_type:
            return None

        if len(potcar_meta := self.potcar_type[0].split("_")) == 2:
            pot_type, func = potcar_meta
        elif len(potcar_meta) == 1:
            pot_type = potcar_meta[0]
            func = "LDA"

        return Potcar(pot_type=pot_type, functional=func, symbols=self.potcar)

    @property
    def xc_override(self) -> str | None:
        """Report the exchange-correlation functional used."""
        xc = None
        if self.incar:
            xc = self.incar.get("GGA") or self.incar.get("METAGGA")
        return xc.upper() if isinstance(xc, str) else xc

    @property
    def magnetic_moments(self) -> list[float] | None:
        """Report initial magnetic moments assigned to each atom."""
        return (self.parameters or {}).get("MAGMOM", None)

    @classmethod
    def from_vasprun(
        cls, vasprun: Vasprun, potcar_spec: list[PotcarSpec] | None = None
    ) -> Self:
        """
        Create a VASP input document from a Vasprun object.

        Parameters
        ----------
        vasprun
            A vasprun object.
        potcar_spec : list of dict
            If specified, the POTCAR spec to override that of vasprun.xml

        Returns
        -------
        CalculationInput
            The input document.
        """
        kpoints_dict = vasprun.kpoints.as_dict()
        kpoints_dict["actual_kpoints"] = [
            {"abc": list(k), "weight": w}
            for k, w in zip(vasprun.actual_kpoints, vasprun.actual_kpoints_weights)
        ]

        parameters = dict(vasprun.parameters).copy()
        incar = dict(vasprun.incar)
        if metagga := incar.get("METAGGA"):
            # Per issue #960, the METAGGA tag is populated in the
            # INCAR field of vasprun.xml, and not parameters
            parameters.update({"METAGGA": metagga})

        return cls(  # type: ignore[call-arg]
            structure=vasprun.initial_structure,
            incar=incar,
            kpoints=Kpoints.from_dict(kpoints_dict),
            nkpoints=len(kpoints_dict["actual_kpoints"]),
            potcar_spec=potcar_spec or [PotcarSpec(**ps) for ps in vasprun.potcar_spec],
            potcar_type=[s.split()[0] for s in vasprun.potcar_symbols],
            parameters=parameters,
            lattice_rec=vasprun.initial_structure.lattice.reciprocal_lattice,
            is_hubbard=vasprun.is_hubbard,
            hubbards=vasprun.hubbards,
        )


class RunStatistics(BaseModel):
    """Summary of the run statistics for a VASP calculation."""

    average_memory: float = Field(0, description="The average memory used in kb")
    max_memory: float = Field(0, description="The maximum memory used in kb")
    elapsed_time: float = Field(0, description="The real time elapsed in seconds")
    system_time: float = Field(0, description="The system CPU time in seconds")
    user_time: float = Field(
        0, description="The user CPU time spent by VASP in seconds"
    )
    total_time: float = Field(0, description="The total CPU time for this calculation")
    cores: int = Field(0, description="The number of cores used by VASP")

    @classmethod
    def from_outcar(cls, outcar: Outcar) -> Self:
        """
        Create a run statistics document from an Outcar object.

        Parameters
        ----------
        outcar
            An Outcar object.

        Returns
        -------
        RunStatistics
            The run statistics.
        """
        # rename these statistics
        mapping = {
            "Average memory used (kb)": "average_memory",
            "Maximum memory used (kb)": "max_memory",
            "Elapsed time (sec)": "elapsed_time",
            "System time (sec)": "system_time",
            "User time (sec)": "user_time",
            "Total CPU time used (sec)": "total_time",
            "cores": "cores",
        }
        run_stats: dict[str, int | float] = {}
        for k, v in mapping.items():
            stat = outcar.run_stats.get(k) or 0
            try:
                stat = float(stat)
            except ValueError:
                # sometimes the statistics are misformatted
                stat = 0

            run_stats[v] = stat

        return cls(**run_stats)  # type: ignore[arg-type]


class FrequencyDependentDielectric(BaseModel):
    """Frequency-dependent dielectric data."""

    real: list[list[float]] | None = Field(
        None,
        description="Real part of the frequency dependent dielectric constant, given at"
        " each energy as 6 components according to XX, YY, ZZ, XY, YZ, ZX",
    )
    imaginary: list[list[float]] | None = Field(
        None,
        description="Imaginary part of the frequency dependent dielectric constant, "
        "given at each energy as 6 components according to XX, YY, ZZ, XY, "
        "YZ, ZX",
    )
    energy: list[float] | None = Field(
        None,
        description="Energies at which the real and imaginary parts of the dielectric"
        "constant are given",
    )

    @classmethod
    def from_vasprun(cls, vasprun: Vasprun) -> Self:
        """
        Create a frequency-dependent dielectric calculation document from a vasprun.

        Parameters
        ----------
        vasprun : Vasprun
            A vasprun object.

        Returns
        -------
        FrequencyDependentDielectric
            A frequency-dependent dielectric document.
        """
        energy, real, imag = vasprun.dielectric
        return cls(real=real, imaginary=imag, energy=energy)


class ElectronPhononDisplacedStructures(BaseModel):
    """Document defining electron phonon displaced structures."""

    temperatures: list[float] | None = Field(
        None,
        description="The temperatures at which the electron phonon displacements "
        "were generated.",
    )
    structures: list[StructureType] | None = Field(
        None, description="The displaced structures corresponding to each temperature."
    )


class IonicStep(BaseModel):  # type: ignore
    """Document defining the information at each ionic step."""

    e_fr_energy: float | None = Field(None, description="The free energy.")
    e_wo_entrp: float | None = Field(None, description="The energy without entropy.")
    e_0_energy: float | None = Field(None, description="The internal energy.")
    forces: list[Vector3D] | None = Field(None, description="The forces on each atom.")
    stress: Matrix3D | None = Field(None, description="The stress on the lattice.")
    electronic_steps: list[ElectronicStep] | None = Field(
        None, description="The electronic convergence steps."
    )
    num_electronic_steps: int | None = Field(
        None, description="The number of electronic steps needed to reach convergence."
    )
    structure: StructureType | None = Field(
        None, description="The structure at this step."
    )

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def set_elec_step_count(self):
        if self.electronic_steps is not None:
            self.num_electronic_steps = len(self.electronic_steps)
        return self


def _deser_dos_properties(
    dos_properties: list[Any] | dict[str, Any] | None,
) -> dict[str, dict[str, dict[str, float]]] | None:
    if dos_properties:
        if isinstance(dos_properties, list):
            dos_properties = {
                element: {
                    orbital: {key: value for key, value in property}
                    for orbital, property in properties
                }
                for element, properties in dos_properties
            }
        elif isinstance(dos_properties, dict) and isinstance(
            next(iter(dos_properties.values())), list
        ):
            dos_properties = {
                element: {
                    orbital: {key: value for key, value in property}
                    for orbital, property in properties
                }
                for element, properties in dos_properties.items()
            }

    return dos_properties  # type: ignore[return-value]


class CoreCalculationOutput(BaseModel):
    """Document defining core VASP calculation outputs."""

    bandgap: float | None = Field(
        None, description="The band gap from the calculation in eV"
    )
    cbm: float | None = Field(
        None,
        description="The conduction band minimum in eV (if system is not metallic)",
    )
    density: float | None = Field(
        None, description="Density of final structure in units of g/cc."
    )
    direct_gap: float | None = Field(
        None, description="Direct band gap in eV (if system is not metallic)"
    )
    dos_properties: Annotated[
        dict[str, dict[str, dict[str, float]]] | None,
        BeforeValidator(_deser_dos_properties),
    ] = Field(
        None,
        description="Element- and orbital-projected band properties (in eV) for the "
        "DOS. All properties are with respect to the Fermi level.",
    )
    efermi: float | None = Field(
        None, description="The Fermi level from the calculation in eV"
    )
    energy: float | None = Field(
        None, description="The final total DFT energy for the calculation"
    )
    energy_per_atom: float | None = Field(
        None, description="The final DFT energy per atom for the calculation"
    )
    epsilon_ionic: ListMatrix3D | None = Field(
        None, description="The ionic part of the dielectric constant"
    )
    epsilon_static: ListMatrix3D | None = Field(
        None, description="The high-frequency dielectric constant"
    )
    epsilon_static_wolfe: ListMatrix3D | None = Field(
        None,
        description="The high-frequency dielectric constant w/o local field effects",
    )
    frequency_dependent_dielectric: FrequencyDependentDielectric | None = Field(
        None,
        description="Frequency-dependent dielectric information from an LOPTICS "
        "calculation",
    )
    is_gap_direct: bool | None = Field(
        None, description="Whether the band gap is direct"
    )
    is_metal: bool | None = Field(None, description="Whether the system is metallic")
    locpot: dict[str, list[float]] | None = Field(
        None, description="Average of the local potential along the crystal axes"
    )
    mag_density: float | None = Field(
        None,
        description="The magnetization density, defined as total_mag/volume "
        "(units of A^-3)",
    )
    optical_absorption_coeff: list[float] | None = Field(
        None, description="Optical absorption coefficient in cm^-1"
    )
    outcar: OutcarType | None = Field(
        None, description="Information extracted from the OUTCAR file"
    )
    structure: StructureType | None = Field(
        None, description="The final structure from the calculation"
    )
    transition: str | None = Field(
        None, description="Band gap transition given by CBM and VBM k-points"
    )
    vbm: float | None = Field(
        None, description="The valence band maximum in eV (if system is not metallic)"
    )


class CalculationOutput(CoreCalculationOutput):
    """Wrapper for CoreCalculationOutput for parsing and storing larger fields."""

    elph_displaced_structures: ElectronPhononDisplacedStructures | None = Field(
        None,
        description="Electron-phonon displaced structures, generated by setting "
        "PHON_LMC = True.",
    )
    force_constants: list[list[Matrix3D]] | None = Field(
        None, description="Force constants between every pair of atoms in the structure"
    )
    ionic_steps: list[IonicStep] | None = Field(
        None, description="Energy, forces, structure, etc. for each ionic step"
    )
    normalmode_eigenvals: list[float] | None = Field(
        None,
        description="Normal mode eigenvalues of phonon modes at Gamma. "
        "Note the unit changed between VASP 5 and 6.",
    )
    normalmode_eigenvecs: list[list[Vector3D]] | None = Field(
        None, description="Normal mode eigenvectors of phonon modes at Gamma"
    )
    normalmode_frequencies: list[float] | None = Field(
        None, description="Frequencies in THz of the normal modes at Gamma"
    )
    num_electronic_steps: list[int] | None = Field(
        None, description="The number of electronic steps in each ionic step."
    )
    run_stats: RunStatistics | None = Field(
        None, description="Summary of runtime statistics for this calculation"
    )

    @classmethod
    def from_vasp_outputs(
        cls,
        vasprun: Vasprun,
        outcar: Outcar | None,
        contcar: Poscar | None,
        locpot: Locpot | None = None,
        elph_poscars: list[Path] | None = None,
        store_trajectory: StoreTrajectoryOption | str = StoreTrajectoryOption.NO,
    ) -> Self:
        """
        Create a VASP output document from VASP outputs.

        Parameters
        ----------
        vasprun
            A Vasprun object.
        outcar
            An Outcar object.
        contcar
            A Poscar object.
        locpot
            A Locpot object.
        elph_poscars
            Path to displaced electron-phonon coupling POSCAR files generated using
            ``PHON_LMC = True``.
        store_trajectory
            Whether to store ionic steps as a pymatgen Trajectory object.
            Different value tune the amount of data from the ionic_steps
            stored in the Trajectory.
            If not NO, the `ionic_steps` field is left as None.
        Returns
        -------
            The VASP calculation output document.
        """
        try:
            bandstructure = vasprun.get_band_structure(efermi="smart")
            bandgap_info = bandstructure.get_band_gap()
            electronic_output = dict(
                efermi=bandstructure.efermi,
                vbm=bandstructure.get_vbm()["energy"],
                cbm=bandstructure.get_cbm()["energy"],
                bandgap=bandgap_info["energy"],
                is_gap_direct=bandgap_info["direct"],
                is_metal=bandstructure.is_metal(),
                direct_gap=bandstructure.get_direct_band_gap(),
                transition=bandgap_info["transition"],
            )
        except Exception:
            logger.warning("Error in parsing bandstructure")
            if vasprun.incar["IBRION"] == 1:
                logger.warning("VASP doesn't properly output efermi for IBRION == 1")
            electronic_output = {}

        freq_dependent_diel: FrequencyDependentDielectric | None = None
        try:
            freq_dependent_diel = FrequencyDependentDielectric.from_vasprun(vasprun)
        except KeyError:
            pass

        locpot_avg = None
        if locpot:
            locpot_avg = {
                str(i): locpot.get_average_along_axis(i).tolist() for i in range(3)
            }

        # parse force constants
        phonon_output = {}
        if hasattr(vasprun, "force_constants"):
            # convert eigenvalues to frequency
            eigs = -vasprun.normalmode_eigenvals
            frequencies = np.sqrt(np.abs(eigs)) * np.sign(eigs)

            # convert to THz in VASP 5 and lower; VASP 6 uses THz internally
            major_version = int(vasprun.vasp_version.split(".")[0])
            if major_version < 6:
                frequencies *= 15.633302

            phonon_output = dict(
                force_constants=vasprun.force_constants.tolist(),
                normalmode_frequencies=frequencies.tolist(),
                normalmode_eigenvals=vasprun.normalmode_eigenvals.tolist(),
                normalmode_eigenvecs=vasprun.normalmode_eigenvecs.tolist(),
            )

        if outcar and contcar:
            outcar_dict = outcar.as_dict()

            # use structure from CONTCAR as it is written to
            # greater precision than in the vasprun
            # but still need to copy the charge over
            structure = contcar.structure
            structure._charge = vasprun.final_structure._charge

            mag_density = (
                outcar.total_mag / structure.volume if outcar.total_mag else None
            )

            if len(outcar.magnetization) != 0:
                # patch calculated magnetic moments into final structure
                magmoms = [m["tot"] for m in outcar.magnetization]
                structure.add_site_property("magmom", magmoms)
        else:
            logger.warning(
                "No OUTCAR/CONTCAR available, some information will be missing from TaskDoc."
            )
            outcar_dict = {}
            structure = vasprun.final_structure
            mag_density = None

        # Parse DOS properties
        dosprop_dict = (
            _get_band_props(vasprun.complete_dos, structure)
            if hasattr(vasprun, "complete_dos") and vasprun.parameters["LORBIT"] >= 11
            else {}
        )

        elph_structures: ElectronPhononDisplacedStructures | None = None
        if elph_poscars is not None:
            elph_structures_dct: dict[str, list[Any]] = {
                "temperatures": [],
                "structures": [],
            }
            for elph_poscar in elph_poscars:
                temp = str(elph_poscar.name).replace("POSCAR.T=", "").replace(".gz", "")
                elph_structures_dct["temperatures"].append(temp)
                elph_structures_dct["structures"].append(
                    Structure.from_file(elph_poscar)
                )
            elph_structures = ElectronPhononDisplacedStructures(**elph_structures_dct)

        store_trajectory = StoreTrajectoryOption(store_trajectory)
        ionic_steps = (
            vasprun.ionic_steps
            if store_trajectory == StoreTrajectoryOption.NO
            else None
        )
        num_elec_steps = None
        if ionic_steps is not None:
            num_elec_steps = [
                len(ionic_step.get("electronic_steps", []) or [])
                for ionic_step in ionic_steps
            ]

        # The `epsilon_*` attrs of vasprun are now numpy arrays
        # and need to be explicitly checked if they are empty
        epsilons: dict[str, np.ndarray | list | None] = {}
        for attr in ("epsilon_static", "epsilon_static_wolfe", "epsilon_ionic"):
            if (v := getattr(vasprun, attr, None)) is not None and len(v) > 0:
                epsilons[attr] = v
            else:
                epsilons[attr] = None

        return cls(
            structure=structure,
            energy=vasprun.final_energy,
            energy_per_atom=vasprun.final_energy / len(structure),
            mag_density=mag_density,
            frequency_dependent_dielectric=freq_dependent_diel,
            elph_displaced_structures=elph_structures,
            dos_properties=dosprop_dict,
            ionic_steps=(
                [IonicStep(**step) for step in ionic_steps] if ionic_steps else None
            ),
            num_electronic_steps=num_elec_steps,
            locpot=locpot_avg,
            outcar=outcar_dict,
            run_stats=RunStatistics.from_outcar(outcar) if outcar else None,
            **epsilons,  # type: ignore[arg-type]
            **electronic_output,
            **phonon_output,
        )


@type_override({"ddec6": str})
class Calculation(CalculationBaseModel):
    """Full VASP calculation inputs and outputs."""

    dir_name: str | None = Field(
        None, description="The directory for this VASP calculation"
    )
    vasp_version: str | None = Field(
        None, description="VASP version used to perform the calculation"
    )
    has_vasp_completed: Annotated[
        TaskState | None,
        BeforeValidator(lambda v: TaskState(v) if v is not None else None),
    ] = Field(None, description="Whether VASP completed the calculation successfully")
    input: CalculationInput | None = Field(
        None, description="VASP input settings for the calculation"
    )
    output: CalculationOutput | None = Field(
        None, description="The VASP calculation output"
    )
    completed_at: str | None = Field(
        None, description="Timestamp for when the calculation was completed"
    )
    task_name: str | None = Field(
        None, description="Name of task given by custodian (e.g., relax1, relax2)"
    )
    output_file_paths: Annotated[
        dict[str, str] | None, BeforeValidator(_dict_items_zipper)
    ] = Field(
        None,
        description="Paths of the VASP output files "
        "associated with this calculation",
    )
    bader: BaderAnalysis | None = Field(
        None, description="Output from bader charge analysis"
    )
    ddec6: JsonDictType = Field(None, description="Output from DDEC6 charge analysis")
    run_type: RunType | None = Field(
        None, description="Calculation run type (e.g., HF, HSE06, PBE)"
    )
    task_type: TaskType | None = Field(
        None, description="Calculation task type (e.g., Structure Optimization)."
    )
    calc_type: CalcType | None = Field(
        None, description="Return calculation type (run type + task_type)."
    )

    @classmethod
    def from_vasp_files(
        cls,
        dir_name: Path | str,
        task_name: str,
        vasprun_file: Path | str,
        outcar_file: Path | str,
        contcar_file: Path | str,
        volumetric_files: list[Path] | None = None,
        elph_poscars: list[Path] | None = None,
        oszicar_file: Path | str | None = None,
        potcar_spec_file: Path | str | None = None,
        parse_dos: str | bool = False,
        parse_bandstructure: str | bool = False,
        average_locpot: bool = True,
        run_bader: bool = False,
        run_ddec6: bool | str = False,
        strip_bandstructure_projections: bool = False,
        strip_dos_projections: bool = False,
        store_volumetric_data: tuple[str] | None = None,
        store_trajectory: StoreTrajectoryOption | str = StoreTrajectoryOption.NO,
        vasprun_kwargs: dict | None = None,
        use_emmet_models: bool = SETTINGS.USE_EMMET_MODELS,
    ) -> tuple[
        "Calculation", dict[VaspObject, ChgcarLike] | dict[VaspObject, VolumetricData]
    ]:
        """
        Create a VASP calculation document from a directory and file paths.

        Parameters
        ----------
        dir_name
            The directory containing the calculation outputs.
        task_name
            The task name.
        vasprun_file
            Path to the vasprun.xml file.
        outcar_file
            Path to the OUTCAR file.
        contcar_file
            Path to the CONTCAR file
        volumetric_files
            Path to volumetric files.
        elph_poscars
            Path to displaced electron-phonon coupling POSCAR files generated using
            ``PHON_LMC = True``
        oszicar_file
            Path to the OSZICAR file
        potcar_spec_file : Path | str | None = None
            Path to a POTCAR.spec file.
            Used in rehydration of a calculation from archived
            data, where the original POTCAR is not available.
        parse_dos
            Whether to parse the DOS. Can be:

            - "auto": Only parse DOS if there are no ionic steps (NSW = 0).
            - True: Always parse DOS.
            - False: Never parse DOS.

        parse_bandstructure
            How to parse the bandstructure. Can be:

            - "auto": Parse the bandstructure with projections for NSCF calculations
              and decide automatically if it's line or uniform mode.
            - "line": Parse the bandstructure as a line mode calculation with
              projections
            - True: Parse the bandstructure as a uniform calculation with
              projections .
            - False: Parse the band structure without projects and just store
              vbm, cbm, band_gap, is_metal and efermi rather than the full
              band structure object.

        average_locpot
            Whether to store the average of the LOCPOT along the crystal axes.
        run_bader : bool = False
            Whether to run bader on the charge density.
        run_ddec6 : bool or str = False
            Whether to run DDEC6 on the charge density. If a string, it's interpreted
            as the path to the atomic densities directory. Can also be set via the
            DDEC6_ATOMIC_DENSITIES_DIR environment variable. The files are available at
            https://sourceforge.net/projects/ddec/files.
        strip_dos_projections
            Whether to strip the element and site projections from the density of
            states. This can help reduce the size of DOS objects in systems with many
            atoms.
        strip_bandstructure_projections
            Whether to strip the element and site projections from the band structure.
            This can help reduce the size of DOS objects in systems with many atoms.
        store_volumetric_data
            Which volumetric files to store.
        store_trajectory
            Whether to store the ionic steps in a pymatgen Trajectory object and the
            amount of data to store from the ionic_steps. Can be:
            - FULL: Store the Trajectory. All the properties from the ionic_steps
              are stored in the frame_properties except for the Structure, to
              avoid redundancy.
            - PARTIAL: Store the Trajectory. All the properties from the ionic_steps
              are stored in the frame_properties except from Structure and
              ElectronicStep.
            - NO: Trajectory is not Stored.
            If not NO, :obj:'.CalculationOutput.ionic_steps' is set to None
            to reduce duplicating information.
        vasprun_kwargs
            Additional keyword arguments that will be passed to the Vasprun init.

        use_emmet_models : bool = True
            Whether to store VASP objects as emmet-core models (True, default)
            or as pymatgen models (False)

        Returns
        -------
        Calculation
            A VASP calculation document.
        """
        dir_name = Path(dir_name)

        vasprun_file = dir_name / vasprun_file
        outcar_file = dir_name / outcar_file
        contcar_file = dir_name / contcar_file

        vasprun_kwargs = vasprun_kwargs if vasprun_kwargs else {}
        volumetric_files = [dir_name / v for v in (volumetric_files or [])]
        vasprun = Vasprun(vasprun_file, **vasprun_kwargs)
        outcar = Outcar(outcar_file)
        if (
            os.path.getsize(contcar_file) == 0
            and vasprun.parameters.get("NELM", 60) == 1
        ):
            contcar = Poscar(vasprun.final_structure)
        else:
            contcar = Poscar.from_file(contcar_file)
        completed_at = str(datetime.fromtimestamp(Path(vasprun_file).stat().st_mtime))

        output_file_paths = _get_output_file_paths(volumetric_files)
        vasp_objects = _get_volumetric_data(
            output_file_paths, store_volumetric_data, use_emmet_models
        )

        if (dos := _parse_dos(parse_dos, vasprun, use_emmet_models)) is not None:
            if strip_dos_projections:
                setattr(
                    dos, "projected_densities" if use_emmet_models else "pdos", None
                )
            vasp_objects[VaspObject.DOS] = dos  # type: ignore

        bandstructure = _parse_bandstructure(
            parse_bandstructure, vasprun, use_emmet_models
        )
        if bandstructure is not None:
            if strip_bandstructure_projections:
                bandstructure.projections = None
            vasp_objects[VaspObject.BANDSTRUCTURE] = bandstructure  # type: ignore

        bader = None
        if run_bader and VaspObject.CHGCAR in output_file_paths:
            suffix = "" if task_name == "standard" else f".{task_name}"
            bader = bader_analysis_from_path(str(dir_name), suffix=suffix)

        ddec6 = None
        if run_ddec6 and VaspObject.CHGCAR in output_file_paths:
            densities_path = run_ddec6 if isinstance(run_ddec6, (str, Path)) else None
            ddec6 = ChargemolAnalysis(
                path=dir_name, atomic_densities_path=densities_path
            ).summary

        locpot: Locpot | None = None
        if average_locpot:
            if VaspObject.LOCPOT in vasp_objects:
                if use_emmet_models:
                    locpot = vasp_objects[VaspObject.LOCPOT].to_pmg(pmg_cls=Locpot)  # type: ignore
                else:
                    locpot = vasp_objects[VaspObject.LOCPOT]  # type: ignore
            elif VaspObject.LOCPOT in output_file_paths:
                locpot_file = output_file_paths[VaspObject.LOCPOT]  # type: ignore
                locpot = Locpot.from_file(locpot_file)

        potcar_spec: list[PotcarSpec] | None = None
        if potcar_spec_file:
            potcar_spec = PotcarSpec.from_file(dir_name / potcar_spec_file)
        input_doc = CalculationInput.from_vasprun(vasprun, potcar_spec=potcar_spec)
        this_task_type = task_type(input_doc.model_dump())

        store_trajectory = StoreTrajectoryOption(store_trajectory)
        output_doc = CalculationOutput.from_vasp_outputs(
            vasprun,
            outcar,
            contcar,
            locpot=locpot,
            elph_poscars=elph_poscars,
            store_trajectory=store_trajectory,
        )

        if store_trajectory != StoreTrajectoryOption.NO:
            temperatures: list[float] | None = None
            if oszicar_file:
                try:
                    oszicar = Oszicar(dir_name / oszicar_file)
                    _temperatures: list[float | None] = [
                        osz_is.get("T") for osz_is in oszicar.ionic_steps
                    ]
                    if all(t is not None for t in _temperatures):
                        temperatures = _temperatures  # type: ignore[assignment]
                except ValueError:
                    # there can be errors in parsing the floats from OSZICAR
                    pass

            traj_class = (
                Trajectory
                if this_task_type == TaskType.Molecular_Dynamics
                else RelaxTrajectory
            )
            vasp_objects[VaspObject.TRAJECTORY] = traj_class.from_vasprun(  # type: ignore[index]
                vasprun,
                store_electronic_steps=(store_trajectory == StoreTrajectoryOption.FULL),
                temperature=temperatures,
            )
            if not use_emmet_models:
                vasp_objects[VaspObject.TRAJECTORY] = vasp_objects[  # type: ignore[union-attr]
                    VaspObject.TRAJECTORY
                ].to_pmg()

        # MD run
        if vasprun.parameters.get("IBRION", -1) == 0:
            if vasprun.parameters.get("NSW", 0) == vasprun.md_n_steps:
                has_vasp_completed = TaskState.SUCCESS
            else:
                has_vasp_completed = TaskState.FAILED
        # others
        else:
            has_vasp_completed = (
                TaskState.SUCCESS if vasprun.converged else TaskState.FAILED
            )

        return (
            cls(
                dir_name=str(dir_name),
                task_name=task_name,
                vasp_version=vasprun.vasp_version,
                has_vasp_completed=has_vasp_completed,
                completed_at=completed_at,
                input=input_doc,
                output=output_doc,
                output_file_paths={
                    k.name.lower(): v for k, v in output_file_paths.items()
                },
                bader=bader,
                ddec6=ddec6,
                run_type=run_type(input_doc.parameters),
                task_type=this_task_type,
                calc_type=calc_type(input_doc.model_dump(), input_doc.parameters),
            ),
            vasp_objects,
        )

    @classmethod
    def from_vasprun(
        cls,
        path: Path | str,
        task_name: str = "Unknown vapsrun.xml",
        vasprun_kwargs: dict | None = None,
    ) -> Self:
        """
        Create a VASP calculation document from a directory and file paths.

        Parameters
        ----------
        path
            Path to the vasprun.xml file.
        task_name
            The task name.
        vasprun_kwargs
            Additional keyword arguments that will be passed to the Vasprun init.

        Returns
        -------
        Calculation
            A VASP calculation document.
        """
        path = Path(path)
        vasprun_kwargs = vasprun_kwargs if vasprun_kwargs else {}
        vasprun = Vasprun(path, **vasprun_kwargs)

        completed_at = str(datetime.fromtimestamp(path.stat().st_mtime))

        input_doc = CalculationInput.from_vasprun(vasprun)

        output_doc = CalculationOutput.from_vasp_outputs(
            vasprun,
            outcar=None,
            contcar=None,
        )

        # MD run
        if vasprun.parameters.get("IBRION", -1) == 0:
            if vasprun.parameters.get("NSW", 0) == vasprun.nionic_steps:
                has_vasp_completed = TaskState.SUCCESS
            else:
                has_vasp_completed = TaskState.FAILED
        # others
        else:
            has_vasp_completed = (
                TaskState.SUCCESS if vasprun.converged else TaskState.FAILED
            )

        return cls(  # type: ignore[call-arg]
            dir_name=str(path.resolve().parent),
            task_name=task_name,
            vasp_version=vasprun.vasp_version,
            has_vasp_completed=has_vasp_completed,
            completed_at=completed_at,
            input=input_doc,
            output=output_doc,
            output_file_paths={},
            run_type=run_type(input_doc.parameters),
            task_type=task_type(input_doc.model_dump()),
            calc_type=calc_type(input_doc.model_dump(), input_doc.parameters),
        )


def _get_output_file_paths(volumetric_files: list[Path]) -> dict[VaspObject, str]:
    """
    Get the output file paths for VASP output files from the list of volumetric files.

    Parameters
    ----------
    volumetric_files
        A list of volumetric files associated with the calculation.

    Returns
    -------
    dict[VaspObject, str]
        A mapping between the VASP object type and the file path.
    """
    return {
        vasp_object: str(volumetric_file)
        for vasp_object in VaspObject
        for volumetric_file in volumetric_files
        if vasp_object.name in str(volumetric_file)
    }


def _get_volumetric_data(
    output_file_paths: dict[VaspObject, str],
    store_volumetric_data: tuple[str] | None,
    use_emmet_models: bool,
) -> dict[VaspObject, ChgcarLike] | dict[VaspObject, VolumetricData]:
    """
    Load volumetric data files from a directory.

    Parameters
    ----------
    output_file_paths
        A dictionary mapping the data type to absolute file paths.
    store_volumetric_data
        The volumetric data files to load. E.g., `("chgcar", "locpot")`.
        Provided as a list of strings note you can use either the keys or the
        values available in the `VaspObject` enum (e.g., "locpot" or "LOCPOT")
        are both valid.
    Whether to store VASP objects as emmet-core models (True, default)
        or as pymatgen models (False)

    Returns
    -------
    dict[VaspObject, ChgcarLike] or dict[VaspObject, VolumetricData]
        A dictionary mapping the VASP object data type (`VaspObject.LOCPOT`,
        `VaspObject.CHGCAR`, etc) to the volumetric data object.
    """
    from pymatgen.io.vasp import Chgcar

    if store_volumetric_data is None or len(store_volumetric_data) == 0:
        return {}

    volumetric_data: dict[VaspObject, ChgcarLike] | dict[VaspObject, VolumetricData] = (
        {}
    )
    for file_type, file in output_file_paths.items():
        if (
            file_type.name not in store_volumetric_data
            and file_type.value not in store_volumetric_data
        ):
            continue

        try:
            # assume volumetric data is all in CHGCAR format
            pmg_cls = Locpot if file_type == VaspObject.LOCPOT else Chgcar
            vobj = pmg_cls.from_file(str(file))
            volumetric_data[file_type] = (
                ChgcarLike.from_pmg(vobj) if use_emmet_models else vobj
            )
        except Exception as exc:
            raise ValueError(f"Failed to parse {file_type} at {file}:\n{exc}.")
    return volumetric_data


def _parse_dos(
    parse_mode: str | bool,
    vasprun: Vasprun,
    use_emmet_models: bool,
) -> ElectronicDos | CompleteDos | None:
    """Parse DOS. See Calculation.from_vasp_files for supported arguments."""
    nsw = vasprun.incar.get("NSW", 0)
    if parse_mode is True or (parse_mode == "auto" and nsw < 1):
        if use_emmet_models:
            return ElectronicDos.from_pmg(vasprun.complete_dos)
        return vasprun.complete_dos
    return None


def _parse_bandstructure(
    parse_mode: str | bool,
    vasprun: Vasprun,
    use_emmet_models: bool,
) -> ElectronicBS | BandStructure | None:
    """Parse band structure. See Calculation.from_vasp_files for supported arguments."""
    vasprun_file = vasprun.filename

    bs: ElectronicBS | BandStructure | None = None
    # only save the bandstructure if not moving ions
    if parse_mode == "auto" and vasprun.incar.get("NSW", 0) <= 1:
        if vasprun.incar.get("ICHARG", 0) > 10:
            # NSCF calculation
            bs_vrun = BSVasprun(vasprun_file, parse_projected_eigen=True)
            try:
                # try parsing line mode
                bs = bs_vrun.get_band_structure(line_mode=True, efermi="smart")
            except Exception:
                # treat as a regular calculation
                bs = bs_vrun.get_band_structure(efermi="smart")
        else:
            # Not a NSCF calculation
            bs_vrun = BSVasprun(vasprun_file, parse_projected_eigen=False)
            bs = bs_vrun.get_band_structure(efermi="smart")

    elif parse_mode:
        # legacy line/True behavior for bandstructure_mode
        bs_vrun = BSVasprun(vasprun_file, parse_projected_eigen=True)
        bs = bs_vrun.get_band_structure(line_mode=parse_mode == "line", efermi="smart")

    if bs and use_emmet_models:
        return ElectronicBS.from_pmg(bs)
    return bs


def _get_band_props(
    complete_dos: CompleteDos, structure: Structure
) -> dict[str, dict[str, dict[str, float]]]:
    """
    Calculate band properties from a CompleteDos object and Structure.

    Parameters
    ----------
    complete_dos
        A CompleteDos object.
    structure
        a pymatgen Structure object.

    Returns
    -------
    dict
        A dictionary of element and orbital-projected DOS properties.
    """
    dosprop_dict: dict[str, dict[str, dict[str, float]]] = {}
    if not complete_dos.pdos:
        # It's possible to have a CompleteDos object with only structure info and no projected DOS info
        return dosprop_dict

    for el in structure.composition.elements:
        el_name = str(el.name)
        dosprop_dict[el_name] = {}

        for orb_type in [
            OrbitalType(x) for x in range(OrbitalType[el.block].value + 1)  # type: ignore[misc]
        ]:
            try:
                dosprop_dict[el_name][str(orb_type)] = {
                    "filling": complete_dos.get_band_filling(
                        band=orb_type, elements=[el]
                    ),
                    "center": complete_dos.get_band_center(
                        band=orb_type, elements=[el]
                    ),
                    "bandwidth": complete_dos.get_band_width(
                        band=orb_type, elements=[el]
                    ),
                    "skewness": complete_dos.get_band_skewness(
                        band=orb_type, elements=[el]
                    ),
                    "kurtosis": complete_dos.get_band_kurtosis(
                        band=orb_type, elements=[el]
                    ),
                    "upper_edge": complete_dos.get_upper_band_edge(
                        band=orb_type, elements=[el]
                    ),
                }
            except KeyError:
                # No projected DOS available for that particular element + orbital character
                continue

    return dosprop_dict


def _calculation_to_trajectory_dict(
    calc: Calculation,
    traj_class: RelaxTrajectory | Trajectory = RelaxTrajectory,
) -> tuple[dict[str, list[Any]], RunType, TaskType, CalcType, float | None]:
    """Convert a single VASP calculation to Trajectory._from_dict compatible dict.

    Parameters
    -----------
    calc (emmet.core.vasp.calculation.Calculation)
    traj_class : RelaxTrajectory
        The trajectory class used in parsing ionic step properties to save.

    Returns
    -----------
    dict, RunType, TaskType, CalcType, float | None
    """

    ct: CalcType | None = None
    rt: RunType | None = None
    tt: TaskType | None = None
    time_step: float | None = None

    ionic_step_props = (
        set(traj_class.model_fields["ionic_step_properties"].default)
        .difference(
            {
                "energy",
                "magmoms",
            }
        )
        .intersection(set(IonicStep.model_fields))
    )

    # refresh calc, run, and task type if possible
    if calc.input:
        vis = calc.input.model_dump()
        padded_params = {
            **(calc.input.parameters or {}),
            **(calc.input.incar or {}),
        }
        ct = calc_type(vis, padded_params)
        rt = run_type(padded_params)
        tt = task_type(vis)
        time_step = (
            padded_params.get("POTIM") if padded_params.get("IBRION", -1) == 0 else None
        )

    props: dict[str, list] = {}

    if calc.output:
        remap = {"energy": "e_0_energy"}
        ionic_steps = calc.output.ionic_steps or []
        props.update(
            {
                k: [getattr(ionic_step, remap.get(k, k)) for ionic_step in ionic_steps]
                for k in {"structure", "energy", *ionic_step_props}
            }
        )

    return props, rt, tt, ct, time_step


def get_trajectories_from_calculations(
    calculations: list[Calculation],
    separate: bool = True,
    traj_class: Type[RelaxTrajectory] = RelaxTrajectory,
    **kwargs,
) -> list[RelaxTrajectory]:
    """
    Create trajectories from a list of Calculation Objects.

    Includes an option to join trajectories with the same `calc_type`.
    Note that if no input is provided in the calculation, the calculation
    is split off into its own trajectory.

    By default, splits every calculation into a separate `Trajectory`.

    Parameters
    -----------
    task_doc : emmet.core.TaskDoc
    separate : bool = True by default
        Whether to split all calculations into separate Trajectory
        objects, or to join them if their calc types are identical.
    traj_class : RelaxTrajectory
        Class to use in deserializing the trajectory data.
        Defaults to RelaxTrajectory, which contains just enough fields
        for a relaxation trajectory.
        Could be used to return a full Trajectory if MD data is desired.
    kwargs
        Other kwargs to pass to Trajectory

    Returns
    -----------
    list of Trajectory
    """

    trajs: list[RelaxTrajectory] = []

    props: dict[str, list[Any]] = {}
    old_meta: dict[str, Any] = {
        k: None for k in ("run_type", "task_type", "calc_type", "time_step")
    }
    new_meta = deepcopy(old_meta)
    for icr, cr in enumerate(calculations):
        (
            new_props,
            new_meta["run_type"],
            new_meta["task_type"],
            new_meta["calc_type"],
            new_meta["time_step"],
        ) = _calculation_to_trajectory_dict(cr, traj_class=traj_class)

        if (
            separate
            or old_meta["calc_type"] != new_meta["calc_type"]
            or new_meta["calc_type"] is None
            or icr == 0
        ):
            # Either CalcType changed or no calculation input was provided
            # or this is the first calculation in `calcs_reversed`
            # Append existing trajectory to list of trajectories, and restart
            if icr > 0:
                trajs.append(traj_class._from_dict(props, **old_meta, **kwargs))  # type: ignore[arg-type]

            props = deepcopy(new_props)
        else:
            for k, new_vals in new_props.items():
                props[k].extend(new_vals)

        for k, v in new_meta.items():
            old_meta[k] = v

    # create final trajectory
    trajs.append(traj_class._from_dict(props, **old_meta, **kwargs))  # type: ignore[arg-type]

    return trajs
