"""Core definition of a Q-Chem Task Document"""

# mypy: ignore-errors
from __future__ import annotations

import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, TYPE_CHECKING

from custodian.qchem.jobs import QCJob
from monty.serialization import loadfn
from pydantic import BaseModel, Field
from pymatgen.core.structure import Molecule
from pymatgen.io.qchem.inputs import QCInput

from emmet.core.qchem.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.qchem.calculation import Calculation, CalculationInput
from emmet.core.qchem.task import QChemStatus
from emmet.core.structure import MoleculeMetadata

if TYPE_CHECKING:
    from typing_extensions import Self

__author__ = (
    "Evan Spotte-Smith <ewcspottesmith@lbl.gov>, Rishabh D. Guha <rdguha@lbl.gov>"
)

logger = logging.getLogger(__name__)
# _DERIVATIVE_FILES = ("GRAD", "HESS")


class OutputDoc(BaseModel):
    initial_molecule: Molecule = Field(None, description="Input Molecule object")
    optimized_molecule: Molecule | None = Field(
        None, description="Optimized Molecule object"
    )

    # TODO: Discuss with Evan if these go here
    # species_hash: str = Field(
    #     None,
    #     description="Weisfeiler Lehman (WL) graph hash using the atom species as the graph node attribute.",
    # )
    # coord_hash: str = Field(
    #     None,
    #     description="Weisfeiler Lehman (WL) graph hash using the atom coordinates as the graph node attribute.",
    # )

    # last_updated: datetime = Field(
    #     None,
    #     description = "Timestamp for the most recent calculation for this QChem task document",
    # )

    final_energy: float = Field(
        None, description="Final electronic energy for the calculation (units: Hartree)"
    )
    enthalpy: float | None = Field(
        None, description="Total enthalpy of the molecule (units: kcal/mol)"
    )
    entropy: float | None = Field(
        None, description="Total entropy of the molecule (units: cal/mol-K"
    )
    dipoles: dict[str, Any] | None = Field(
        None, description="Dipolar information from the output"
    )
    mulliken: list[Any] | None = Field(
        None, description="Mulliken atomic partial charges and partial spins"
    )
    resp: list[float | list[Any]] | None = Field(
        None,
        description="Restrained Electrostatic Potential (RESP) atomic partial charges",
    )
    nbo: dict[str, Any] | None = Field(
        None, description="Natural Bonding Orbital (NBO) output"
    )

    frequencies: dict[str, Any] | list | None = Field(
        None,
        description="The list of calculated frequencies if job type is freq (units: cm^-1)",
    )

    frequency_modes: list | str | None = Field(
        None,
        description="The list of calculated frequency mode vectors if job type is freq",
    )

    @classmethod
    def from_qchem_calc_doc(cls, calc_doc: Calculation) -> "OutputDoc":
        """
        Create a summary of QChem calculation outputs from a QChem calculation document.

        Parameters
        ----------
        calc_doc
            A QChem calculation document.
        kwargs
            Any other additional keyword arguments

        Returns
        --------
        OutputDoc
            The calculation output summary
        """
        return cls(
            initial_molecule=calc_doc.input.initial_molecule,
            optimized_molecule=calc_doc.output.optimized_molecule,
            # species_hash = self.species_hash, #The three entries post this needs to be checked again
            # coord_hash = self.coord_hash,
            # last_updated = self.last_updated,
            final_energy=calc_doc.output.final_energy,
            dipoles=calc_doc.output.dipoles,
            enthalpy=calc_doc.output.enthalpy,
            entropy=calc_doc.output.entropy,
            mulliken=calc_doc.output.mulliken,
            resp=calc_doc.output.resp,
            nbo=calc_doc.output.nbo_data,
            frequencies=calc_doc.output.frequencies,
            frequency_modes=calc_doc.output.frequency_modes,
        )


class InputDoc(BaseModel):
    initial_molecule: Molecule = Field(
        None,
        title="Input Structure",
        description="Input molecule and calc details for the QChem calculation",
    )

    prev_rem_params: dict[str, Any] | None = Field(
        None,
        description="Parameters from a previous qchem calculation in the series",
    )

    rem: dict[str, Any] = Field(
        None,
        description="Parameters from the rem section of the current QChem calculation",
    )

    level_of_theory: str | LevelOfTheory | None = Field(
        None, description="Level of theory used in the qchem calculation"
    )

    task_type: str | TaskType | None = Field(
        None,
        description="The type of the QChem calculation : optimization, single point ... etc.",
    )

    tags: list[str] | None = Field(
        None, title="tag", description="Metadata tagged to a given task."
    )

    solvation_lot_info: dict[str, Any] | str | None = Field(
        None,
        description="Str or Dict representation of the solvent method used for the calculation",
    )

    special_run_type: str | None = Field(
        None, description="Special workflow name (if applicable)"
    )

    smiles: str | None = Field(
        None,
        description="Simplified molecular-input line-entry system (SMILES) string for the molecule involved "
        "in this calculation.",
    )

    calc_type: str | CalcType | None = Field(
        None,
        description="A combined dictionary representation of the task type along with the level of theory used",
    )

    @classmethod
    def from_qchem_calc_doc(cls, calc_doc: Calculation) -> "InputDoc":
        """
        Create qchem calculation input summary from a qchem calculation document.

        Parameters
        ----------
        calc_doc
            A QChem calculation document.

        Returns
        --------
        InputDoc
            A summary of the input molecule and corresponding calculation parameters
        """
        try:
            lot_val = calc_doc.level_of_theory.value
        except AttributeError:
            lot_val = calc_doc.level_of_theory

        try:
            ct_val = calc_doc.calc_type.value
        except AttributeError:
            ct_val = calc_doc.calc_type
        # TODO : modify this to get the different variables from the task doc.
        return cls(
            initial_molecule=calc_doc.input.initial_molecule,
            rem=calc_doc.input.rem,
            level_of_theory=lot_val,
            task_type=calc_doc.task_type.value,
            tags=calc_doc.input.tags,
            solvation_lot_info=calc_doc.solvation_lot_info,
            # special_run_type = calc_doc.input.special_run_type,
            # smiles = calc_doc.input.smiles,
            calc_type=ct_val,
        )


class CustodianDoc(BaseModel):
    corrections: list[Any] | None = Field(
        None,
        title="Custodian Corrections",
        description="List of custodian correction data for calculation.",
    )

    job: dict[str, Any] | QCJob | None = Field(
        None,
        title="Custodian Job Data",
        description="Job data logged by custodian.",
    )


# AnalysisDoc? Is there a scope for AnalysisDoc in QChem?


class TaskDoc(MoleculeMetadata):
    """
    Calculation-level details about QChem calculations that would eventually take over the TaskDocument implementation
    """

    dir_name: str | Path | None = Field(
        None, description="The directory for this QChem task"
    )

    state: QChemStatus | None = Field(
        None, description="State of this QChem calculation"
    )

    calcs_reversed: list[Calculation] | None = Field(
        None,
        title="Calcs reversed data",
        description="Detailed data for each QChem calculation contributing to the task document.",
    )

    task_type: CalcType | TaskType | None = Field(
        None, description="the type of QChem calculation"
    )

    orig_inputs: CalculationInput | dict[str, Any] | None = Field(
        {}, description="Summary of the original Q-Chem inputs"
    )

    input: InputDoc | None = Field(
        None,
        description="The input molecule and calc parameters used to generate the current task document.",
    )

    output: OutputDoc | None = Field(
        None,
        description="The exact set of output parameters used to generate the current task document.",
    )

    # TODO: Implement entry dict

    custodian: list[CustodianDoc] | None = Field(
        None,
        title="Calcs reversed data",
        description="Detailed custodian data for each QChem calculation contributing to the task document.",
    )

    critic2: dict[str, Any] | None = Field(
        None, description="Outputs from the critic2 calculation if performed"
    )

    custom_smd: str | dict[str, Any] | None = Field(
        None,
        description="The seven solvent parameters necessary to define a custom_smd model",
    )

    additional_fields: dict[str, Any] | None = Field(
        None, description="Any miscellaneous fields passed to the pydantic model"
    )

    # TODO some sort of @validator s if necessary

    @classmethod
    def from_directory(
        cls,
        dir_name: Path | str,
        validate_lot: bool = True,
        store_additional_json: bool = True,
        additional_fields: dict[str, Any] = None,
        **qchem_calculation_kwargs,
    ) -> Self:
        """
        Create a task document from a directory containing QChem files.

        Parameters
        ----------
        dir_name
            The path to the folder containing the calculation outputs.
        validate_lot
            Flag for matching the basis and functional with the list of functionals consistent with MPCules.
            Defaults to True. Change to False if you want to create a TaskDoc with other basis sets and functionals.
        store_additional_json
            Whether to store additional json files in the calculation directory.
        additional_fields
            Dictionary of additional fields to add to output document.
        **qchem_calculation_kwargs
            Additional parsing options that will be passed to the
            :obj:`.Calculation.from_qchem_files` function.

        Returns
        -------
        QChemTaskDoc
            A task document for the calculation
        """
        logger.info(f"Getting task doc in: {dir_name}")

        additional_fields = {} if additional_fields is None else additional_fields
        dir_name = Path(dir_name)
        task_files = _find_qchem_files(dir_name)

        if len(task_files) == 0:
            raise FileNotFoundError("No QChem files found!")

        critic2 = {}
        custom_smd = {}
        calcs_reversed = []
        for task_name, files in task_files.items():
            if task_name == "orig":
                continue
            else:
                calc_doc = Calculation.from_qchem_files(
                    dir_name,
                    task_name,
                    **files,
                    **qchem_calculation_kwargs,
                    validate_lot=validate_lot,
                )
                calcs_reversed.append(calc_doc)
                # all_qchem_objects.append(qchem_objects)

        # Lists need to be reversed so that newest calc is the first calc, all_qchem_objects are also reversed to match
        calcs_reversed.reverse()

        # all_qchem_objects.reverse()
        custodian = _parse_custodian(dir_name)
        additional_json = None
        if store_additional_json:
            additional_json = _parse_additional_json(dir_name)
            for key, _ in additional_json.items():
                if key == "processed_critic2":
                    critic2["processed"] = additional_json["processed_critic2"]
                elif key == "cpreport":
                    critic2["cp"] = additional_json["cpreport"]
                elif key == "YT":
                    critic2["yt"] = additional_json["yt"]
                elif key == "bonding":
                    critic2["bonding"] = additional_json["bonding"]
                elif key == "solvent_data":
                    custom_smd = additional_json["solvent_data"]

        orig_inputs = (
            CalculationInput.from_qcinput(_parse_orig_inputs(dir_name))
            if _parse_orig_inputs(dir_name)
            else {}
        )

        dir_name = get_uri(dir_name)  # convert to full path

        # only store objects from last calculation
        # TODO: If vasp implementation makes this an option, change here as well
        qchem_objects = None
        included_objects = None
        if qchem_objects:
            included_objects = list(qchem_objects.keys())

        # run_stats = _get_run_stats(calcs_reversed), Discuss whether this is something which is necessary in terms of QChem calcs
        doc = cls.from_molecule(
            meta_molecule=calcs_reversed[-1].input.initial_molecule,
            dir_name=dir_name,
            calcs_reversed=calcs_reversed,
            custodian=custodian,
            additional_json=additional_json,
            additional_fields=additional_fields,
            completed_at=calcs_reversed[0].completed_at,
            orig_inputs=orig_inputs,
            input=InputDoc.from_qchem_calc_doc(calcs_reversed[0]),
            output=OutputDoc.from_qchem_calc_doc(calcs_reversed[0]),
            state=_get_state(calcs_reversed),
            qchem_objects=qchem_objects,
            included_objects=included_objects,
            critic2=critic2,
            custom_smd=custom_smd,
            task_type=calcs_reversed[0].task_type,
        )

        # doc = doc.copy(update=additional_fields)
        doc = doc.model_copy(update=additional_fields)
        return doc

    @staticmethod
    def get_entry(
        calcs_reversed: list[Calculation], task_id: str | None = None
    ) -> dict:
        """
        Get a computed entry from a list of QChem calculation documents.

        Parameters
        ----------
        calcs_reversed
            A list of QChem calculation documents in reverse order.
        task_id
            The job identifier

        Returns
        --------
        Dict
            A dict of computed entries
        """

        entry_dict = {
            "entry_id": task_id,
            "task_id": task_id,
            "charge": calcs_reversed[0].output.molecule.charge,
            "spin_multiplicity": calcs_reversed[0].output.molecule.spin_multiplicity,
            "level_of_theory": calcs_reversed[-1].input.level_of_theory,
            "solvent": calcs_reversed[-1].input.solv_spec,
            "lot_solvent": calcs_reversed[-1].input.lot_solv_combo,
            "custom_smd": calcs_reversed[-1].input.custom_smd,
            "task_type": calcs_reversed[-1].input.task_spec,
            "calc_type": calcs_reversed[-1].input.calc_spec,
            "tags": calcs_reversed[-1].input.tags,
            "molecule": calcs_reversed[0].output.molecule,
            "composition": calcs_reversed[0].output.molecule.composition,
            "formula": calcs_reversed[
                0
            ].output.formula.composition.aplhabetical_formula,
            "energy": calcs_reversed[0].output.final_energy,
            "output": calcs_reversed[0].output.as_dict(),
            "critic2": calcs_reversed[
                0
            ].output.critic,  # TODO: Unclear about orig_inputs
            "last_updated": calcs_reversed[0].output.last_updated,
        }

        return entry_dict


def get_uri(dir_name: str | Path) -> str:
    """
    Return the URI path for a directory.

    This allows files hosted on different file servers to have distinct locations.

    Parameters
    ----------
    dir_name : str or Path
        A directory name.

    Returns
    -------
    str
        Full URI path, e.g., "fileserver.host.com:/full/payj/of/fir_name".
    """
    import socket

    fullpath = Path(dir_name).absolute()
    hostname = socket.gethostname()
    try:
        hostname = socket.gethostbyaddr(hostname)[0]
    except (socket.gaierror, socket.herror):
        pass
    return f"{hostname}:{fullpath}"


def _parse_custodian(dir_name: Path) -> dict | None:
    """
    Parse custodian.json file.

    Calculations done using custodian have a custodian.json file which tracks the makers
    performed and any errors detected and fixed.

    Parameters
    ----------
    dir_name
        Path to calculation directory.

    Returns
    --------
    dict | None
        The information parsed from custodian.json file.
    """
    filenames = tuple(dir_name.glob("custodian.json*"))
    if len(filenames) >= 1:
        return loadfn(filenames[0], cls=None)
    return None


def _parse_orig_inputs(
    dir_name: Path,
) -> dict[str, Any]:
    """
    Parse original input files.

    Calculations using custodian generate a *.orig file for the inputs. This is useful
    to know how the calculation originally started.

    Parameters
    ----------
    dir_name
        Path to calculation directory.

    Returns
    -------
    dict[str, Any]
        The original molecule, rem, solvent and other data.
    """
    orig_inputs = {}
    orig_file_path = next(dir_name.glob("*.orig*"), None)

    if orig_file_path:
        orig_inputs = QCInput.from_file(orig_file_path)

    return orig_inputs


def _parse_additional_json(dir_name: Path) -> dict[str, Any]:
    """Parse additional json files in the directory."""
    additional_json = {}
    for filename in dir_name.glob("*.json*"):
        key = filename.name.split(".")[0]
        if key not in ("custodian", "transformations"):
            if key not in additional_json:
                additional_json[key] = loadfn(filename, cls=None)
    return additional_json


def _get_state(calcs_reversed: list[Calculation]) -> QChemStatus:
    """Get state from calculation documents of QChem tasks."""
    all_calcs_completed = all(
        [c.has_qchem_completed == QChemStatus.SUCCESS for c in calcs_reversed]
    )
    if all_calcs_completed:
        return QChemStatus.SUCCESS
    return QChemStatus.FAILED


# def _get_run_stats(calcs_reversed: list[Calculation]) -> dict[str, RunStatistics]:
#     """Get summary of runtime statistics for each calculation in this task."""

#     run_stats = {}
#     total = dict(
#         average_memory=0.0,
#         max_memory=0.0,
#         elapsed_time=0.0,
#         system_time=0.0,
#         user_time=0.0,
#         total_time=0.0,
#         cores=0,
#     )


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
