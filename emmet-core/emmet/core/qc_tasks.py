# mypy: ignore-errors

""" Core definition of a Q-Chem Task Document """
from typing import Any, Dict, List, Optional
import logging
import os
import re
from collections import OrderedDict
from pydantic import BaseModel, Field
from pymatgen.core.structure import Molecule
from pymatgen.io.qchem.inputs import QCInput
from monty.serialization import loadfn
from typing import Type, TypeVar, Union
from emmet.core.structure import MoleculeMetadata
from pathlib import Path
from emmet.core.qchem.calc_types import (
    LevelOfTheory,
    CalcType,
    TaskType,
)
from emmet.core.qchem.calculation import Calculation

from emmet.core.qchem.task import QChemStatus


__author__ = (
    "Evan Spotte-Smith <ewcspottesmith@lbl.gov>, Rishabh D. Guha <rdguha@lbl.gov>"
)

logger = logging.getLogger(__name__)
_T = TypeVar("_T", bound="TaskDoc")
# _DERIVATIVE_FILES = ("GRAD", "HESS")


# class QChemStatus(ValueEnum):
#     """
#     Q-Chem Calculation State
#     """

#     SUCCESS = "successful"
#     FAILED = "unsuccessful"


class OutputDoc(BaseModel):
    molecule: Molecule = Field(
        None,
        title="Output Molecule",
        description="Output molecule after the QChem Calculation",
    )

    initial_molecule: Molecule = Field(None, description="Input Molecule object")
    optimized_molecule: Molecule = Field(None, description="Optimized Molecule object")

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
    enthalpy: float = Field(
        None, description="Total enthalpy of the molecule (units: kcal/mol)"
    )
    entropy: float = Field(
        None, description="Total entropy of the molecule (units: cal/mol-K"
    )

    mulliken: List[Any] = Field(
        None, description="Mulliken atomic partial charges and partial spins"
    )
    resp: List[float] = Field(
        None,
        description="Restrained Electrostatic Potential (RESP) atomic partial charges",
    )
    nbo: Dict[str, Any] = Field(
        None, description="Natural Bonding Orbital (NBO) output"
    )

    frequencies: List[float] = Field(
        None, description="Vibrational frequencies of the molecule (units: cm^-1)"
    )

    @classmethod
    def from_qchem_calc_doc(self, cls, calc_doc: Calculation, **kwargs) -> "OutputDoc":
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
            enthalpy=calc_doc.output.enthalpy,
            entropy=calc_doc.output.entropy,
            mulliken=calc_doc.output.mulliken,
            resp=calc_doc.output.resp,
            nbo=calc_doc.output.nbo_data,
            frequencies=calc_doc.output.frequencies,
        )


class InputDoc(BaseModel):
    molecule: Molecule = Field(
        None,
        title="Input Structure",
        description="Input molecule and calc details for the QChem calculation",
    )

    prev_rem_params: Dict = Field(
        None,
        description="Parameters from a previous qchem calculation in the series",
    )

    lev_theory: LevelOfTheory = Field(
        None, description="Level of theory used in the qchem calculation"
    )

    task_type: TaskType = Field(
        None,
        description="The type of the QChem calculation : optimization, single point ... etc.",
    )

    tags: Union[List[str], None] = Field(
        [], title="tag", description="Metadata tagged to a given task."
    )

    solvent: Dict = Field(
        None,
        description="Dictionary with the implicit solvent model and respective parameters",
    )

    lot_solvent: str = Field(
        None,
        description="A string representation with the combined information of the solvemt used and the level of theory",
    )

    custom_smd: str = Field(
        None, description="Parameter string for SMD implicit solvent model"
    )

    special_run_type: str = Field(
        None, description="Special workflow name (if applicable)"
    )

    smiles: str = Field(
        None,
        description="Simplified molecular-input line-entry system (SMILES) string for the molecule involved "
        "in this calculation.",
    )

    calc_type: CalcType = Field(
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
        # TODO : modify this to get the different variables from the task doc.
        return cls(
            initial_molecule=calc_doc.input.initial_molecule,
            rem=calc_doc.input.rem,
            # lev_theory = level_of_theory(calc_doc.input.rem),
            task_type=calc_doc.task_type,
            tags=calc_doc.input.tags,
            solvent=calc_doc.input.solvent,
            # lot_solvent_string = calc_doc.input.lot_solvent_string,
            # custom_smd = calc_doc.input.custom_smd,
            # special_run_type = calc_doc.input.special_run_type,
            # smiles = calc_doc.input.smiles,
            calc_spec=calc_doc.calc_type,
        )


class CustodianDoc(BaseModel):
    corrections: List[Any] = Field(
        None,
        title="Custodian Corrections",
        description="List of custodian correction data for calculation.",
    )

    job: dict = Field(
        None,
        title="Custodian Job Data",
        description="Job data logged by custodian.",
    )


# AnalysisDoc? Is there a scope for AnalysisDoc in QChem?


class TaskDoc(MoleculeMetadata):
    """
    Calculation-level details about QChem calculations that would eventually take over the TaskDocument implementation
    """

    dir_name: str = Field(None, description="The directory for this QChem task")

    state: QChemStatus = Field(None, description="State of this QChem calculation")

    calcs_reversed: List[Calculation] = Field(
        None,
        title="Calcs reversed data",
        description="Detailed data for each QChem calculation contributing to the task document.",
    )

    molecule: Molecule = Field(
        None, description="Final optimized/output molecule from this task"
    )

    task_type: Union[CalcType, TaskType] = Field(
        None, description="the type of QChem calculation"
    )

    orig: Dict[str, Any] = Field(
        {}, description="Summary of the original Q-Chem inputs"
    )

    input: InputDoc = Field(
        None,
        description="The input molecule and calc parameters used to generate the current task document.",
    )

    output: OutputDoc = Field(
        None,
        description="The exact set of output parameters used to generate the current task document.",
    )

    # TODO: Implement entry dict

    custodian: List[CustodianDoc] = Field(
        None,
        title="Calcs reversed data",
        description="Detailed custodian data for each QChem calculation contributing to the task document.",
    )

    critic2: Dict[str, Any] = Field(
        None, description="Outputs from the critic2 calculation if performed"
    )

    custom_smd: Union(str, Dict[str, Any]) = Field(
        None,
        description="The seven solvent parameters necessary to define a custom_smd model",
    )

    # TODO some sort of @validator s if necessary

    @classmethod
    def from_directory(
        cls: Type[_T],
        dir_name: Union[Path, str],
        store_additional_json: bool = True,
        additional_fields: Dict[str, Any] = None,
        **qchem_calculation_kwargs,
    ) -> _T:
        """
        Create a task document from a directory containing QChem files.

        Parameters
        ----------
        dir_name
            The path to the folder containing the calculation outputs.
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
        calcs_reversed = []
        all_qchem_objects = []
        for task_name, files in task_files.items():
            calc_doc, qchem_objects = Calculation.from_qchem_files(
                dir_name, task_name, **files, **qchem_calculation_kwargs
            )
            calcs_reversed.append(calc_doc)
            all_qchem_objects.append(qchem_objects)

        # Lists need to be reversed so that newest calc is the first calc, all_qchem_objects are also reversed to match
        calcs_reversed.reverse()
        all_qchem_objects.reverse()
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

        orig_inputs = _parse_orig_inputs(dir_name)

        dir_name = get_uri(dir_name)  # convert to full path

        # only store objects from last calculation
        # TODO: If vasp implementation makes this an option, change here as well
        qchem_objects = all_qchem_objects[0]
        included_objects = None
        if qchem_objects:
            included_objects = list(qchem_objects.keys())

        # run_stats = _get_run_stats(calcs_reversed), Discuss whether this is something which is necessary in terms of QChem calcs

        doc = cls.from_molecule(
            molecule=calcs_reversed[0].output.molecule,
            meta_molecule=calcs_reversed[0].output.molecule,
            include_molecule=True,
            dir_name=dir_name,
            calcs_reversed=calcs_reversed,
            custodian=custodian,
            additional_json=additional_json,
            completed_at=calcs_reversed[0].completed_at,
            orig_inputs=orig_inputs,
            input=InputDoc.from_qchem_calc_doc(calcs_reversed[-1]),
            output=OutputDoc.from_qchem_calc_doc(calcs_reversed[0]),
            state=_get_state(calcs_reversed),
            qchem_objects=qchem_objects,
            included_objects=included_objects,
            critic2=critic2,
            custom_smd=custom_smd,
            task_type=calcs_reversed[0].task_type,
        )
        doc = doc.copy(update=additional_fields)
        return doc

    @staticmethod
    def get_entry(
        calcs_reversed: List[Calculation], task_id: Optional[str] = None
    ) -> Dict:
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
            "level_of_theory": calcs_reversed[-1].input.lev_theory,
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


def get_uri(dir_name: Union[str, Path]) -> str:
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


def _parse_custodian(dir_name: Path) -> Optional[Dict]:
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
    Optional[Dict]
        The information parsed from custodian.json file.
    """
    filenames = tuple(dir_name.glob("custodian.json*"))
    if len(filenames) >= 1:
        return loadfn(filenames[0], cls=None)
    return None


def _parse_orig_inputs(
    dir_name: Path,
) -> Dict[str, Any]:
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
    Dict[str, Any]
        The original molecule, rem, solvent and other data.
    """
    orig_inputs = {}
    for filename in dir_name.glob("*.orig*"):
        orig_inputs = QCInput.from_file(os.path.join(dir_name, filename.pop("orig")))
        return orig_inputs


def _parse_additional_json(dir_name: Path) -> Dict[str, Any]:
    """Parse additional json files in the directory."""
    additional_json = {}
    for filename in dir_name.glob("*.json*"):
        key = filename.name.split(".")[0]
        if key not in ("custodian", "transformations"):
            if key not in additional_json:
                additional_json[key] = loadfn(filename, cls=None)
    return additional_json


def _get_state(calcs_reversed: List[Calculation]) -> QChemStatus:
    """Get state from calculation documents of QChem tasks."""
    all_calcs_completed = all(
        [c.has_qchem_completed == QChemStatus.SUCCESS for c in calcs_reversed]
    )
    if all_calcs_completed:
        return QChemStatus.SUCCESS
    return QChemStatus.FAILED


# def _get_run_stats(calcs_reversed: List[Calculation]) -> Dict[str, RunStatistics]:
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
    path: Union[str, Path],
) -> Dict[str, Any]:
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
    Dict[str, Any]
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
    print(Path)

    in_file_pattern = re.compile(r"^(?P<in_task_name>mol\.qin(?:\..+)?)\.gz$")
    print(in_file_pattern)

    for file in path.iterdir():
        if file.is_file():
            print(file.name)
            in_match = in_file_pattern.match(file.name)
            print(in_match)
            # out_match = out_file_pattern.match(file.name)
            if in_match:
                # print(in_task_name)
                in_task_name = in_match.group("in_task_name").replace("mol.qin.", "")
                print(in_task_name)
                # out_task_name = out_match.group('out_task_name').replace("mol.qout", "") #Remove mol.qout
                if in_task_name == "orig":
                    task_files[in_task_name] = {"orig_input_file": file}
                elif in_task_name == "mol.qin":
                    task_files["standard"] = {
                        "qchem_in_file": file,
                        "qchem_out_file": Path("mol.qout.gz"),
                    }
                else:
                    try:
                        task_files[in_task_name] = {
                            "qchem_in_file": file,
                            "qchem_out_file": Path("mol.qout." + in_task_name + ".gz"),
                        }
                    except FileNotFoundError:
                        task_files[in_task_name] = {
                            "qchem_in_file": file,
                            "qchem_out_file": "No qout files exist for this in file",
                        }

    return task_files
