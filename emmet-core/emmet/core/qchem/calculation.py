"""Core definitions of a QChem calculation document."""

from __future__ import annotations

import logging
import re
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymatgen.core.structure import Molecule
from pymatgen.io.qchem.inputs import QCInput
from pymatgen.io.qchem.outputs import QCOutput

from emmet.core.qchem.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.qchem.calc_types.calc_types import BASIS_SETS, FUNCTIONALS
from emmet.core.qchem.task import QChemStatus
from emmet.core.utils import arrow_incompatible

# from emmet.core.qchem.calc_types.em_utils import (
#     level_of_theory,
#     task_type,
#     calc_type,
# )


functional_synonyms = {
    "b97mv": "b97m-v",
    "b97mrv": "b97m-rv",
    "wb97xd": "wb97x-d",
    "wb97xd3": "wb97x-d3",
    "wb97xv": "wb97x-v",
    "wb97mv": "wb97m-v",
}

smd_synonyms = {
    "DIELECTRIC=7,230;N=1,410;ALPHA=0,000;BETA=0,859;GAMMA=36,830;PHI=0,000;PSI=0,000": "diglyme",
    "DIELECTRIC=18,500;N=1,415;ALPHA=0,000;BETA=0,735;GAMMA=20,200;PHI=0,000;PSI=0,000": "3:7 EC:EMC",
}

__author__ = "Rishabh D. Guha <rdguha@lbl.gov>"
logger = logging.getLogger(__name__)

# class QChemObject(ValueEnum):
# Not sure but can we have something like GRAD and HESS
# as QChem data objects


@arrow_incompatible
class CalculationInput(BaseModel):
    """
    Document defining QChem calculation inputs.
    """

    initial_molecule: Molecule | None = Field(
        None, description="input molecule geometry before the QChem calculation"
    )

    # parameters: dict[str, Any] = Field(
    #     None, description = "Parameters from a previous QChem calculation."
    # )

    charge: int | None = Field(None, description="The charge of the input molecule")

    rem: dict[str, Any] | None = Field(
        None,
        description="The rem dict of the input file which has all the input parameters",
    )

    job_type: str | None = Field(
        None, description="The type of QChem calculation being performed"
    )

    opt: dict[str, Any] | None = Field(
        None,
        description="A dictionary of opt section. For instance atom constraints and fixed atoms. Go to QCInput definition for more details.",
    )

    pcm: dict[str, Any] | None = Field(
        None, description="A dictionary for the PCM solvent details if used"
    )

    solvent: dict[str, Any] | None = Field(
        None,
        description="The solvent parameters used if the PCM solvent model has been employed",
    )

    smx: dict[str, Any] | None = Field(
        None,
        description="A dictionary for the solvent parameters if the SMD solvent method has been employed",
    )

    vdw_mode: str | None = Field(
        None,
        description="Either atomic or sequential. Used when custon van der Waals radii are used to construct pcm cavity",
    )

    van_der_waals: dict[str, Any] | None = Field(
        None, description="The dictionary of the custom van der Waals radii if used"
    )

    scan_variables: dict[str, Any] | None = Field(
        None,
        description="The dictionary of scan variables for torsions or bond stretches",
    )

    tags: dict[str, Any] | str | None = Field(
        None, description="Any tags associated with the QChem calculation."
    )

    @classmethod
    def from_qcinput(cls, qcinput: QCInput) -> "CalculationInput":
        """
        Create a QChem input document from a QCInout object.

        Parameters
        ----------
        qcinput
            A QCInput object.

        Returns
        --------
        CalculationInput
            The input document.
        """

        # QCInput.molecule is either a Molecule, list of Molecule, or a str-literal
        # Catch latter two cases here and error out
        if not isinstance(qcinput.molecule, Molecule):
            raise ValueError("QCInput contains multiple molecules.")

        return cls(  # type: ignore[call-arg]
            initial_molecule=qcinput.molecule,
            charge=(
                int(qcinput.molecule.as_dict()["charge"])
                if qcinput.molecule.as_dict()
                else None
            ),
            rem=qcinput.rem,
            job_type=qcinput.rem.get("job_type", None),
            opt=qcinput.opt,
            pcm=qcinput.pcm,
            solvent=qcinput.solvent,
            smx=qcinput.smx,
            vdw_mode=qcinput.vdw_mode,
            scan_variables=qcinput.scan,
            van_der_waals=qcinput.van_der_waals,
        )


@arrow_incompatible
class CalculationOutput(BaseModel):
    """Document defining QChem calculation outputs."""

    optimized_molecule: Molecule | None = Field(
        None,
        description="optimized geometry of the molecule after calculation in case of opt, optimization or ts",
    )

    mulliken: list | dict[str, Any] | None = Field(
        None, description="Calculate Mulliken charges on the atoms"
    )

    esp: list | dict[str, Any] | None = Field(
        None,
        description="Calculated charges on the atoms if esp calculation has been performed",
    )

    resp: list | dict[str, Any] | None = Field(
        None,
        description="Calculated charges on the atoms if resp calculation has been performed",
    )

    nbo_data: dict[str, Any] | None = Field(
        None, description="NBO data if analysis has been performed."
    )

    frequencies: dict[str, Any] | list | None = Field(
        None,
        description="Calculated frequency modes if the job type is freq or frequency",
    )

    frequency_modes: list | str | None = Field(
        None, description="The list of calculated frequency mode vectors"
    )

    final_energy: str | float | None = Field(
        None,
        description="The final energy of the molecule after the calculation is complete",
    )

    enthalpy: str | float | None = Field(
        None,
        description="The total enthalpy correction if a frequency calculation has been performed",
    )

    entropy: str | float | None = Field(
        None,
        description="The total entropy of the system if a frequency calculation has been performed",
    )

    scan_energies: dict[str, Any] | None = Field(
        None,
        description="A dictionary of the scan energies with their respective parameters",
    )

    scan_geometries: list | dict[str, Any] | None = Field(
        None, description="optimized geometry of the molecules after the geometric scan"
    )

    scan_molecules: list | dict[str, Any] | Molecule | None = Field(
        None,
        description="The constructed pymatgen molecules from the optimized scan geometries",
    )

    pcm_gradients: dict[str, Any] | np.ndarray | list | None = Field(
        None,
        description="The parsed total gradients after adding the PCM contributions.",
    )

    @field_validator("pcm_gradients", mode="before")
    @classmethod
    def validate_pcm_gradients(cls, v):
        if v is not None and not isinstance(v, (np.ndarray, dict, list)):
            raise ValueError(
                "pcm_gradients must be a numpy array, a dict or a list or None."
            )
        return v

    cds_gradients: dict[str, Any] | np.ndarray | list | None = Field(
        None, description="The parsed CDS gradients."
    )

    @field_validator("cds_gradients", mode="before")
    @classmethod
    def validate_cds_gradients(cls, v):
        if v is not None and not isinstance(v, (np.ndarray, dict, list)):
            raise ValueError(
                "cds_gradients must be a numpy array, a dict or a list or None."
            )
        return v

    dipoles: dict[str, Any] | None = Field(
        None, description="The associated dipoles for Mulliken/RESP/ESP charges"
    )

    gap_info: dict[str, Any] | None = Field(
        None, description="The Kohn-Sham HOMO-LUMO gaps and associated Eigenvalues"
    )

    @classmethod
    def from_qcoutput(cls, qcoutput: QCOutput) -> "CalculationOutput":
        """
        Create a QChem output document from a QCOutput object.

        Parameters
        ----------
        qcoutput
            A QCOutput object.

        Returns
        --------
        CalculationOutput
            The output document.
        """
        optimized_molecule = qcoutput.data.get("molecule_from_optimized_geometry", {})
        optimized_molecule = optimized_molecule if optimized_molecule else None
        return cls(
            optimized_molecule=optimized_molecule,
            mulliken=qcoutput.data.get(["Mulliken"][-1], []),
            esp=qcoutput.data.get(["ESP"][-1], []),
            resp=qcoutput.data.get(["RESP"][-1], []),
            nbo_data=qcoutput.data.get("nbo_data", {}),
            frequencies=qcoutput.data.get("frequencies", {}),
            frequency_modes=qcoutput.data.get("frequency_mode_vectors", []),
            final_energy=qcoutput.data.get("final_energy", None),
            enthalpy=qcoutput.data.get("total_enthalpy", None),
            entropy=qcoutput.data.get("total_entropy", None),
            scan_energies=qcoutput.data.get("scan_energies", {}),
            scan_geometries=qcoutput.data.get("optimized_geometries", {}),
            scan_molecules=qcoutput.data.get("molecules_from_optimized_geometries", {}),
            pcm_gradients=qcoutput.data.get(["pcm_gradients"][0], None),
            cds_gradients=qcoutput.data.get(["CDS_gradients"][0], None),
            dipoles=qcoutput.data.get("dipoles", None),
            gap_info=qcoutput.data.get("gap_info", None),
        )

    model_config = ConfigDict(arbitrary_types_allowed=True)
    # TODO What can be done for the trajectories, also how will walltime and cputime be reconciled


@arrow_incompatible
class Calculation(BaseModel):
    """Full QChem calculation inputs and outputs."""

    dir_name: str = Field(description="The directory for this QChem calculation")
    qchem_version: str | None = Field(
        None, description="QChem version used to perform the current calculation"
    )
    has_qchem_completed: QChemStatus | bool | None = Field(
        None, description="Whether QChem calculated the calculation successfully"
    )
    input: CalculationInput | None = Field(
        None, description="QChem input settings for the calculation"
    )
    output: CalculationOutput | None = Field(
        None, description="The QChem calculation output document"
    )
    completed_at: str | None = Field(
        None, description="Timestamp for when the calculation was completed"
    )
    task_name: str | None = Field(
        None,
        description="Name of task given by custodian (e.g. opt1, opt2, freq1, freq2)",
    )
    output_file_paths: dict[str, str | Path | dict[str, Path]] | None = Field(
        None,
        description="Paths (relative to dir_name) of the QChem output files associated with this calculation",
    )
    level_of_theory: LevelOfTheory | str = Field(
        None,
        description="Levels of theory used for the QChem calculation: For instance, B97-D/6-31g*",
    )
    solvation_lot_info: str | None = Field(
        None,
        description="A condensed string representation of the comboned LOT and Solvent info",
    )
    task_type: TaskType | None = Field(
        None,
        description="Calculation task type like Single Point, Geometry Optimization. Frequency...",
    )
    calc_type: CalcType | str | None = Field(
        None,
        description="Combination dict of LOT + TaskType: B97-D/6-31g*/VACUUM Geometry Optimization",
    )

    @classmethod
    def from_qchem_files(
        cls,
        dir_name: Path | str,
        task_name: str,
        qcinput_file: Path | str,
        qcoutput_file: Path | str,
        validate_lot: bool = True,
        store_energy_trajectory: bool = False,
        qcinput_kwargs: dict | None = None,
        qcoutput_kwargs: dict | None = None,
    ) -> "Calculation":
        """
        Create a QChem calculation document from a directory and file paths.

        Parameters
        ----------
        dir_name
            The directory containing the QChem calculation outputs.
        task_name
            The task name.
        qcinput_file
            Path to the .in/qin file, relative to dir_name.
        qcoutput_file
            Path to the .out/.qout file, relative to dir_name.
        store_energy_trajectory
            Whether to store the energy trajectory during a QChem calculation #TODO: Revisit this- False for now.
        qcinput_kwargs
            Additional keyword arguments that will be passed to the qcinput file
        qcoutput_kwargs
            Additional keyword arguments that will be passed to the qcoutput file

        Returns
        -------
        Calculation
            A QChem calculation document.
        """

        dir_name = Path(dir_name)
        qcinput_file = dir_name / qcinput_file
        qcoutput_file = dir_name / qcoutput_file

        output_file_paths = _find_qchem_files(dir_name)

        qcinput_kwargs = qcinput_kwargs if qcinput_kwargs else {}
        qcinput = QCInput.from_file(qcinput_file, **qcinput_kwargs)

        qcoutput_kwargs = qcoutput_kwargs if qcoutput_kwargs else {}
        qcoutput = QCOutput(str(qcoutput_file), **qcoutput_kwargs)

        completed_at = str(datetime.fromtimestamp(qcoutput_file.stat().st_mtime))

        input_doc = CalculationInput.from_qcinput(qcinput)
        output_doc = CalculationOutput.from_qcoutput(qcoutput)

        has_qchem_completed = (
            QChemStatus.SUCCESS
            if qcoutput.data.get("completion", [])
            else QChemStatus.FAILED
        )

        if store_energy_trajectory:
            warnings.warn("Still have to figure the energy trajectory")

        return cls(
            dir_name=str(dir_name),
            task_name=task_name,
            qchem_version=qcoutput.data["version"],
            has_qchem_completed=has_qchem_completed,
            completed_at=completed_at,
            input=input_doc,
            output=output_doc,
            output_file_paths={
                k.lower(): (
                    Path(v)
                    if isinstance(v, str)
                    else {k2: Path(v2) for k2, v2 in v.items()}
                )
                for k, v in output_file_paths.items()
            },
            level_of_theory=level_of_theory(input_doc, validate_lot=validate_lot),
            solvation_lot_info=lot_solvent_string(input_doc, validate_lot=validate_lot),
            task_type=task_type(input_doc),
            calc_type=calc_type(input_doc, validate_lot=validate_lot),
        )


def _find_qchem_files(
    path: str | Path,
) -> dict[str, Any]:
    """
    Find QChem files in a directory.

    Only the mol.qout file (or alternatively files
    with the task name as an extension, e.g., mol.qout.opt_0.gz, mol.qout.freq_1.gz, or something like this...)
    will be returned.

    Parameters
    ----------
    path
        Path to a directory to search.

    Returns
    -------
    dict[str, Any]
        The filenames of the calculation outputs for each QChem task, given as a ordered dictionary of::

            {
                task_name:{
                    "qchem_out_file": qcrun_filename,
                },
                ...
            }
    If there is only 1 qout file task_name will be "standard" otherwise it will be the extension name like "opt_0"
    """
    path = Path(path)
    task_files = OrderedDict()

    in_file_pattern = re.compile(r"^(?P<in_task_name>mol\.(qin|in)(?:\..+)?)(\.gz)?$")

    for file in path.iterdir():
        if file.is_file():
            in_match = in_file_pattern.match(file.name)

            # This block is for generalizing outputs coming from both atomate and manual qchem calculations
            if in_match:
                in_task_name = re.sub(
                    r"(\.gz|gz)$",
                    "",
                    in_match.group("in_task_name").replace("mol.qin.", ""),
                )
                in_task_name = in_task_name or "mol.qin"
                if in_task_name == "orig":
                    task_files[in_task_name] = {"orig_input_file": file.name}
                elif in_task_name == "last":
                    continue
                elif in_task_name == "mol.qin" or in_task_name == "mol.in":
                    if in_task_name == "mol.qin":
                        out_file = (
                            path / "mol.qout.gz"
                            if (path / "mol.qout.gz").exists()
                            else path / "mol.qout"
                        )
                    else:
                        out_file = (
                            path / "mol.out.gz"
                            if (path / "mol.out.gz").exists()
                            else path / "mol.out"
                        )
                    task_files["standard"] = {
                        "qcinput_file": file.name,
                        "qcoutput_file": out_file.name,
                    }
                # This block will exist only if calcs were run through atomate
                else:
                    try:
                        task_files[in_task_name] = {
                            "qcinput_file": file.name,
                            "qcoutput_file": Path(
                                "mol.qout." + in_task_name + ".gz"
                            ).name,
                        }
                    except FileNotFoundError:
                        task_files[in_task_name] = {
                            "qcinput_file": file.name,
                            "qcoutput_file": "No qout files exist for this in file",
                        }

    return task_files


def level_of_theory(
    parameters: CalculationInput, validate_lot: bool = True
) -> LevelOfTheory:
    """

    Returns the level of theory for a calculation,
    based on the input parameters given to Q-Chem

    Args:
        parameters: dict of Q-Chem input parameters

    """

    rem_pars = parameters.rem or {}
    funct_raw = rem_pars.get("method")
    basis_raw = rem_pars.get("basis")

    if funct_raw is None or basis_raw is None:
        raise ValueError(
            'Method and basis must be included in "rem" section ' "of parameters!"
        )

    disp_corr = rem_pars.get("dft_d")

    if disp_corr is None:
        funct_lower = funct_raw.lower()
        funct_lower = functional_synonyms.get(funct_lower, funct_lower)
    else:
        # Replace Q-Chem terms for D3 tails with more common expressions
        disp_corr = disp_corr.replace("_bj", "(bj)").replace("_zero", "(0)")
        funct_lower = f"{funct_raw}-{disp_corr}"

    basis_lower = basis_raw.lower()

    solvent_method = rem_pars.get("solvent_method", "").lower()

    if solvent_method == "":
        solvation = "VACUUM"
    elif solvent_method in ["pcm", "cosmo"]:
        solvation = "PCM"
    # TODO: Add this once added into pymatgen and atomate
    # elif solvent_method == "isosvp":
    #     if parameters.get("svp", {}).get("idefesr", 0):
    #         solvation = "CMIRS"
    #     else:
    #         solvation = "ISOSVP"
    elif solvent_method == "smd":
        solvation = "SMD"
    else:
        raise ValueError(f"Unexpected implicit solvent method {solvent_method}!")

    if validate_lot:
        # --> TODO: replace with enums
        functional = [f for f in FUNCTIONALS if f.lower() == funct_lower]
        if not functional:
            raise ValueError(f"Unexpected functional {funct_lower}!")

        functional = functional[0]

        basis = [b for b in BASIS_SETS if b.lower() == basis_lower]
        if not basis:
            raise ValueError(f"Unexpected basis set {basis_lower}!")

        basis = basis[0]
        # <--

        lot = f"{functional}/{basis}/{solvation}"

        return LevelOfTheory(lot)
    else:
        warnings.warn(
            "User has turned the validate flag off."
            "This can have downstream effects if the chosen functional and basis "
            "is not in the available sets of MP employed functionals and the user"
            "wants to include the TaskDoc in the MP infrastructure."
            "Users should ignore this warning if their objective is just to create TaskDocs",
            UserWarning,
            stacklevel=2,
        )
        functional = funct_lower
        basis = basis_lower
        lot = f"{functional}/{basis}/{solvation}"

        return lot


def solvent(
    parameters: CalculationInput,
    validate_lot: bool = True,
    custom_smd: str | None = None,
) -> str:
    """
    Returns the solvent used for this calculation.

    Args:
        parameters: dict of Q-Chem input parameters
        custom_smd: (Optional) string representing SMD parameters for a
        non-standard solvent
    """
    lot = level_of_theory(parameters, validate_lot=validate_lot)
    if validate_lot:
        solvation = lot.value.split("/")[-1]
    else:
        solvation = lot.split("/")[-1]

    if solvation == "PCM":
        # dielectric = float(parameters.get("solvent", {}).get("dielectric", 78.39))
        # dielectric = float(parameters.get("solvent", {}))
        # dielectric = getattr(parameters, "solvent", None)
        # dielectric_string = f"{dielectric.get('dielectric', '0.0'):.2f}".replace(".", ",")
        dielectric_string = getattr(parameters, "solvent", None)
        return f"DIELECTRIC= {dielectric_string}"
    # TODO: Add this once added into pymatgen and atomate
    # elif solvation == "ISOSVP":
    #     dielectric = float(parameters.get("svp", {}).get("dielst", 78.39))
    #     rho = float(parameters.get("svp", {}).get("rhoiso", 0.001))
    #     return f"DIELECTRIC={round(dielectric, 2)},RHO={round(rho, 4)}"
    # elif solvation == "CMIRS":
    #     dielectric = float(parameters.get("svp", {}).get("dielst", 78.39))
    #     rho = float(parameters.get("svp", {}).get("rhoiso", 0.001))
    #     a = parameters.get("pcm_nonels", {}).get("a")
    #     b = parameters.get("pcm_nonels", {}).get("b")
    #     c = parameters.get("pcm_nonels", {}).get("c")
    #     d = parameters.get("pcm_nonels", {}).get("d")
    #     solvrho = parameters.get("pcm_nonels", {}).get("solvrho")
    #     gamma = parameters.get("pcm_nonels", {}).get("gamma")
    #
    #     string = f"DIELECTRIC={round(dielectric, 2)},RHO={round(rho, 4)}"
    #     for name, (piece, digits) in {"A": (a, 6), "B": (b, 6), "C": (c, 1), "D": (d, 3),
    #                                   "SOLVRHO": (solvrho, 2), "GAMMA": (gamma, 1)}.items():
    #         if piece is None:
    #             piecestring = "NONE"
    #         else:
    #             piecestring = f"{name}={round(float(piece), digits)}"
    #         string += "," + piecestring
    #     return string
    elif solvation == "SMD":
        solvent = (parameters.smx or {}).get("solvent", "water")
        if solvent == "other":
            if custom_smd is None:
                raise ValueError(
                    "SMD calculation with solvent=other requires custom_smd!"
                )

            names = ["DIELECTRIC", "N", "ALPHA", "BETA", "GAMMA", "PHI", "PSI"]
            numbers = [float(x) for x in custom_smd.split(",")]

            string = ""
            for name, number in zip(names, numbers):
                string += f"{name}={number:.3f};"
            return string.rstrip(",").rstrip(";").replace(".", ",")
        else:
            return f"SOLVENT={solvent.upper()}"
    else:
        return "NONE"


def lot_solvent_string(
    parameters: CalculationInput,
    validate_lot: bool = True,
    custom_smd: str | None = None,
) -> str:
    """
    Returns a string representation of the level of theory and solvent used for this calculation.

    Args:
        parameters: dict of Q-Chem input parameters
        custom_smd: (Optional) string representing SMD parameters for a
        non-standard solvent
    """
    if validate_lot:
        lot = level_of_theory(parameters, validate_lot=validate_lot).value
    else:
        lot = level_of_theory(parameters, validate_lot=validate_lot)
    solv = solvent(parameters, custom_smd=custom_smd, validate_lot=validate_lot)
    return f"{lot}({solv})"


def task_type(
    parameters: CalculationInput, special_run_type: str | None = None
) -> TaskType:
    if special_run_type == "frequency_flattener":
        return TaskType("Frequency Flattening Geometry Optimization")
    elif special_run_type == "ts_frequency_flattener":
        return TaskType("Frequency Flattening Transition State Geometry Optimization")

    if parameters.job_type == "sp":
        return TaskType("Single Point")
    elif parameters.job_type == "force":
        return TaskType("Force")
    elif parameters.job_type == "opt":
        return TaskType("Geometry Optimization")
    elif parameters.job_type == "ts":
        return TaskType("Transition State Geometry Optimization")
    elif parameters.job_type == "freq":
        return TaskType("Frequency Analysis")

    return TaskType("Unknown")


def calc_type(
    parameters: CalculationInput,
    validate_lot: bool = True,
    special_run_type: str | None = None,
) -> CalcType:
    """
    Determines the calc type

    Args:
        parameters: CalculationInput parameters
    """
    tt = task_type(parameters, special_run_type=special_run_type).value
    if validate_lot:
        rt = level_of_theory(parameters, validate_lot=validate_lot).value
        return CalcType(f"{rt} {tt}")
    else:
        rt = level_of_theory(parameters, validate_lot=validate_lot)
        return str(f"{rt} {tt}")
