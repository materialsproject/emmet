# mypy: ignore-errors

import logging
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union

import numpy as np
from monty.json import MontyDecoder
from monty.serialization import loadfn
from pydantic import field_validator, ConfigDict, BaseModel, Field, model_validator
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.core.structure import Structure
from pymatgen.core.trajectory import Trajectory
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from pymatgen.io.vasp import Incar, Kpoints, Poscar
from pymatgen.io.vasp import Potcar as VaspPotcar

from emmet.core.structure import StructureMetadata
from emmet.core.vasp.calc_types import CalcType, TaskType
from emmet.core.vasp.calculation import (
    Calculation,
    PotcarSpec,
    RunStatistics,
    VaspObject,
)
from emmet.core.vasp.task_valid import TaskState

monty_decoder = MontyDecoder()
logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound="TaskDoc")
_VOLUMETRIC_FILES = ("CHGCAR", "LOCPOT", "AECCAR0", "AECCAR1", "AECCAR2")


class Potcar(BaseModel):
    pot_type: Optional[str] = Field(None, description="Pseudo-potential type, e.g. PAW")
    functional: Optional[str] = Field(
        None, description="Functional type use in the calculation."
    )
    symbols: Optional[List[str]] = Field(
        None, description="List of VASP potcar symbols used in the calculation."
    )


class OrigInputs(BaseModel):
    incar: Optional[Union[Incar, Dict]] = Field(
        None,
        description="Pymatgen object representing the INCAR file.",
    )

    poscar: Optional[Poscar] = Field(
        None,
        description="Pymatgen object representing the POSCAR file.",
    )

    kpoints: Optional[Kpoints] = Field(
        None,
        description="Pymatgen object representing the KPOINTS file.",
    )

    potcar: Optional[Union[Potcar, VaspPotcar, List[Any]]] = Field(
        None,
        description="Pymatgen object representing the POTCAR file.",
    )

    @field_validator("potcar", mode="before")
    @classmethod
    def potcar_ok(cls, v):
        if isinstance(v, list):
            return [i for i in v]
        return v

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OutputDoc(BaseModel):
    structure: Optional[Structure] = Field(
        None,
        title="Output Structure",
        description="Output Structure from the VASP calculation.",
    )

    density: Optional[float] = Field(None, description="Density of in units of g/cc.")
    energy: float = Field(..., description="Total Energy in units of eV.")
    forces: Optional[List[List[float]]] = Field(
        None, description="The force on each atom in units of eV/A^2."
    )
    stress: Optional[List[List[float]]] = Field(
        None, description="The stress on the cell in units of kB."
    )
    energy_per_atom: Optional[float] = Field(
        None, description="The final DFT energy per atom for the last calculation"
    )
    bandgap: Optional[float] = Field(
        None, description="The DFT bandgap for the last calculation"
    )

    @model_validator(mode="before")
    def set_density_from_structure(cls, values):
        # Validator to automatically set density from structure if not already
        # specified. This might happen when importing an older atomate2-format
        # TaskDocument.
        if not values.get("density", None):
            values["density"] = values["structure"].density
        return values

    @classmethod
    def from_vasp_calc_doc(
        cls, calc_doc: Calculation, trajectory: Optional[Trajectory] = None
    ) -> "OutputDoc":
        """
        Create a summary of VASP calculation outputs from a VASP calculation document.

        This will first look for ionic steps in the calculation document. If found, will
        use it and ignore the trajectory. I not, will get ionic steps from the
        trajectory.

        Parameters
        ----------
        calc_doc
            A VASP calculation document.
        trajectory
            A pymatgen Trajectory.

        Returns
        -------
        OutputDoc
            The calculation output summary.
        """
        if calc_doc.output.ionic_steps is not None:
            forces = calc_doc.output.ionic_steps[-1].forces
            stress = calc_doc.output.ionic_steps[-1].stress
        elif trajectory is not None:
            ionic_steps = trajectory.frame_properties
            forces = ionic_steps[-1]["forces"]
            stress = ionic_steps[-1]["stress"]
        else:
            raise RuntimeError("Unable to find ionic steps.")

        return cls(
            structure=calc_doc.output.structure,
            energy=calc_doc.output.energy,
            energy_per_atom=calc_doc.output.energy_per_atom,
            bandgap=calc_doc.output.bandgap,
            forces=forces,
            stress=stress,
        )


class InputDoc(BaseModel):
    structure: Optional[Structure] = Field(
        None,
        title="Input Structure",
        description="Output Structure from the VASP calculation.",
    )

    parameters: Optional[Dict] = Field(
        None,
        description="Parameters from vasprun for the last calculation in the series",
    )
    pseudo_potentials: Optional[Potcar] = Field(
        None, description="Summary of the pseudo-potentials used in this calculation"
    )
    potcar_spec: Optional[List[PotcarSpec]] = Field(
        None, description="Title and hash of POTCAR files used in the calculation"
    )
    xc_override: Optional[str] = Field(
        None, description="Exchange-correlation functional used if not the default"
    )
    is_lasph: Optional[bool] = Field(
        None, description="Whether the calculation was run with aspherical corrections"
    )
    is_hubbard: bool = Field(False, description="Is this a Hubbard +U calculation")
    hubbards: Optional[dict] = Field(None, description="The hubbard parameters used")

    @classmethod
    def from_vasp_calc_doc(cls, calc_doc: Calculation) -> "InputDoc":
        """
        Create calculation input summary from a calculation document.

        Parameters
        ----------
        calc_doc
            A VASP calculation document.

        Returns
        -------
        InputDoc
            A summary of the input structure and parameters.
        """
        xc = calc_doc.input.incar.get("GGA")
        if xc:
            xc = xc.upper()

        pot_type, func = calc_doc.input.potcar_type[0].split("_")
        func = "lda" if len(pot_type) == 1 else "_".join(func)
        pps = Potcar(pot_type=pot_type, functional=func, symbols=calc_doc.input.potcar)
        return cls(
            structure=calc_doc.input.structure,
            parameters=calc_doc.input.parameters,
            pseudo_potentials=pps,
            potcar_spec=calc_doc.input.potcar_spec,
            is_hubbard=calc_doc.input.is_hubbard,
            hubbards=calc_doc.input.hubbards,
            xc_override=xc,
            is_lasph=calc_doc.input.parameters.get("LASPH", False),
        )


class CustodianDoc(BaseModel):
    corrections: Optional[List[Any]] = Field(
        None,
        title="Custodian Corrections",
        description="List of custodian correction data for calculation.",
    )
    job: Optional[dict] = Field(
        None,
        title="Cusotodian Job Data",
        description="Job data logged by custodian.",
    )


class AnalysisDoc(BaseModel):
    delta_volume: Optional[float] = Field(
        None,
        title="Volume Change",
        description="Volume change for the calculation.",
    )
    delta_volume_percent: Optional[float] = Field(
        None,
        title="Volume Change Percent",
        description="Percent volume change for the calculation.",
    )
    max_force: Optional[float] = Field(
        None,
        title="Max Force",
        description="Maximum force on any atom at the end of the calculation.",
    )

    warnings: Optional[List[str]] = Field(
        None,
        title="Calculation Warnings",
        description="Warnings issued after analysis.",
    )

    errors: Optional[List[str]] = Field(
        None,
        title="Calculation Errors",
        description="Errors issued after analysis.",
    )

    @classmethod
    def from_vasp_calc_docs(
        cls,
        calcs_reversed: List[Calculation],
        volume_change_warning_tol: float = 0.2,
    ) -> "AnalysisDoc":
        """
        Create analysis summary from VASP calculation documents.

        Parameters
        ----------
        calcs_reversed
            A list of VASP calculation documents in reverse order .
        volume_change_warning_tol
            Maximum volume change allowed in VASP relaxations before the calculation is
            tagged with a warning.

        Returns
        -------
        AnalysisDoc
            The relaxation analysis.
        """
        initial_vol = calcs_reversed[-1].input.structure.lattice.volume
        final_vol = calcs_reversed[0].output.structure.lattice.volume
        delta_vol = final_vol - initial_vol
        percent_delta_vol = 100 * delta_vol / initial_vol
        warnings = []
        errors = []

        if abs(percent_delta_vol) > volume_change_warning_tol * 100:
            warnings.append(f"Volume change > {volume_change_warning_tol * 100}%")

        final_calc = calcs_reversed[0]
        max_force = None
        if final_calc.has_vasp_completed == TaskState.SUCCESS:
            # max force and valid structure checks
            structure = final_calc.output.structure
            # do not check max force for MD run
            if calcs_reversed[0].input.parameters.get("IBRION", -1) != 0:
                max_force = _get_max_force(final_calc)
            warnings.extend(_get_drift_warnings(final_calc))
            if not structure.is_valid():
                errors.append("Bad structure (atoms are too close!)")

        return cls(
            delta_volume=delta_vol,
            delta_volume_percent=percent_delta_vol,
            max_force=max_force,
            warnings=warnings,
            errors=errors,
        )


class TaskDoc(StructureMetadata, extra="allow"):
    """
    Calculation-level details about VASP calculations that power Materials Project.
    """

    tags: Union[List[str], None] = Field(
        [], title="tag", description="Metadata tagged to a given task."
    )
    dir_name: Optional[str] = Field(
        None, description="The directory for this VASP task"
    )

    state: Optional[TaskState] = Field(None, description="State of this calculation")

    calcs_reversed: Optional[List[Calculation]] = Field(
        None,
        title="Calcs reversed data",
        description="Detailed data for each VASP calculation contributing to the task document.",
    )

    structure: Optional[Structure] = Field(
        None, description="Final output structure from the task"
    )

    task_type: Optional[Union[CalcType, TaskType]] = Field(
        None, description="The type of calculation."
    )

    task_id: Optional[str] = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    orig_inputs: Optional[OrigInputs] = Field(
        None,
        description="The exact set of input parameters used to generate the current task document.",
    )

    input: Optional[InputDoc] = Field(
        None,
        description="The input structure used to generate the current task document.",
    )

    output: Optional[OutputDoc] = Field(
        None,
        description="The exact set of output parameters used to generate the current task document.",
    )

    included_objects: Optional[List[VaspObject]] = Field(
        None, description="List of VASP objects included with this task document"
    )
    vasp_objects: Optional[Dict[VaspObject, Any]] = Field(
        None, description="Vasp objects associated with this task"
    )
    entry: Optional[ComputedEntry] = Field(
        None, description="The ComputedEntry from the task doc"
    )

    task_label: Optional[str] = Field(None, description="A description of the task")
    author: Optional[str] = Field(
        None, description="Author extracted from transformations"
    )
    icsd_id: Optional[Union[str, int]] = Field(
        None, description="Inorganic Crystal Structure Database id of the structure"
    )
    transformations: Optional[Dict[str, Any]] = Field(
        None,
        description="Information on the structural transformations, parsed from a "
        "transformations.json file",
    )
    additional_json: Optional[Dict[str, Any]] = Field(
        None, description="Additional json loaded from the calculation directory"
    )

    custodian: Optional[List[CustodianDoc]] = Field(
        None,
        title="Calcs reversed data",
        description="Detailed custodian data for each VASP calculation contributing to the task document.",
    )

    analysis: Optional[AnalysisDoc] = Field(
        None,
        title="Calculation Analysis",
        description="Some analysis of calculation data after collection.",
    )

    last_updated: Optional[datetime] = Field(
        None,
        description="Timestamp for the most recent calculation for this task document",
    )

    # Make sure that the datetime field is properly formatted
    # (Unclear when this is not the case, please leave comment if observed)
    @field_validator("last_updated", mode="before")
    @classmethod
    def last_updated_dict_ok(cls, v) -> datetime:
        return v if isinstance(v, datetime) else monty_decoder.process_decoded(v)

    @model_validator(mode="after")
    def set_entry(self) -> datetime:
        if not self.entry and (self.calcs_reversed and self.task_id):
            self.entry = self.get_entry(self.calcs_reversed, self.task_id)
        return self

    @classmethod
    def from_directory(
        cls: Type[_T],
        dir_name: Union[Path, str],
        volumetric_files: Tuple[str, ...] = _VOLUMETRIC_FILES,
        store_additional_json: bool = True,
        additional_fields: Dict[str, Any] = None,
        volume_change_warning_tol: float = 0.2,
        **vasp_calculation_kwargs,
    ) -> _T:
        """
        Create a task document from a directory containing VASP files.

        Parameters
        ----------
        dir_name
            The path to the folder containing the calculation outputs.
        store_additional_json
            Whether to store additional json files found in the calculation directory.
        volumetric_files
            Volumetric files to search for.
        additional_fields
            Dictionary of additional fields to add to output document.
        volume_change_warning_tol
            Maximum volume change allowed in VASP relaxations before the calculation is
            tagged with a warning.
        **vasp_calculation_kwargs
            Additional parsing options that will be passed to the
            :obj:`.Calculation.from_vasp_files` function.

        Returns
        -------
        TaskDoc
            A task document for the calculation.
        """
        logger.info(f"Getting task doc in: {dir_name}")

        additional_fields = {} if additional_fields is None else additional_fields
        dir_name = Path(dir_name)
        task_files = _find_vasp_files(dir_name, volumetric_files=volumetric_files)

        if len(task_files) == 0:
            raise FileNotFoundError("No VASP files found!")

        calcs_reversed = []
        all_vasp_objects = []
        for task_name, files in task_files.items():
            calc_doc, vasp_objects = Calculation.from_vasp_files(
                dir_name, task_name, **files, **vasp_calculation_kwargs
            )
            calcs_reversed.append(calc_doc)
            all_vasp_objects.append(vasp_objects)

        # Reverse the list of calculations in the order:  newest calc is the first
        # To match with calcs_reversed, all_vasp_objects is also reversed.
        calcs_reversed.reverse()
        all_vasp_objects.reverse()

        analysis = AnalysisDoc.from_vasp_calc_docs(
            calcs_reversed, volume_change_warning_tol=volume_change_warning_tol
        )
        transformations, icsd_id, tags, author = _parse_transformations(dir_name)
        custodian = _parse_custodian(dir_name)
        orig_inputs = _parse_orig_inputs(dir_name)

        additional_json = None
        if store_additional_json:
            additional_json = _parse_additional_json(dir_name)

        dir_name = get_uri(dir_name)  # convert to full uri path

        # only store objects from last calculation
        # TODO: make this an option
        vasp_objects = all_vasp_objects[0]
        included_objects = None
        if vasp_objects:
            included_objects = list(vasp_objects.keys())

        doc = cls.from_structure(
            structure=calcs_reversed[0].output.structure,
            meta_structure=calcs_reversed[0].output.structure,
            include_structure=True,
            dir_name=dir_name,
            calcs_reversed=calcs_reversed,
            analysis=analysis,
            transformations=transformations,
            custodian=custodian,
            orig_inputs=orig_inputs,
            additional_json=additional_json,
            icsd_id=icsd_id,
            tags=tags,
            author=author,
            completed_at=calcs_reversed[0].completed_at,
            input=InputDoc.from_vasp_calc_doc(calcs_reversed[-1]),
            output=OutputDoc.from_vasp_calc_doc(
                calcs_reversed[0],
                vasp_objects.get(VaspObject.TRAJECTORY),  # type: ignore
            ),
            state=_get_state(calcs_reversed, analysis),
            run_stats=_get_run_stats(calcs_reversed),
            vasp_objects=vasp_objects,
            included_objects=included_objects,
            task_type=calcs_reversed[0].task_type,
        )
        doc = doc.model_copy(update=additional_fields)
        return doc

    @classmethod
    def from_vasprun(
        cls: Type[_T],
        path: Union[str, Path],
        additional_fields: Dict[str, Any] = None,
        volume_change_warning_tol: float = 0.2,
        **vasp_calculation_kwargs,
    ) -> _T:
        """
        Create a task document from a vasprun.xml file.

        This is not recommended and will raise warnings, since some necessary
        information is absent from the vasprun.xml file, such as per-atom
        magnetic moments. However, the majority of the TaskDoc will
        be complete.

        Parameters
        ----------
        path
            The path to the vasprun.xml.
        additional_fields: Dict[str, Any] = None,
        volume_change_warning_tol
            Maximum volume change allowed in VASP relaxations before the calculation is
            tagged with a warning.
        **vasp_calculation_kwargs
            Additional parsing options that will be passed to the
            :obj:`.Calculation.from_vasp_files` function.

        Returns
        -------
        TaskDoc
            A task document for the calculation.
        """
        logger.info(f"Getting vasprun.xml at: {path}")

        path = Path(path)
        dir_name = path.resolve().parent

        calc = Calculation.from_vasprun(path, **vasp_calculation_kwargs)
        calcs_reversed = [calc]

        analysis = AnalysisDoc.from_vasp_calc_docs(
            calcs_reversed, volume_change_warning_tol=volume_change_warning_tol
        )

        # assume orig_inputs are those stated in vasprun.xml
        orig_inputs = OrigInputs(
            incar=calc.input.incar,
            poscar=Poscar(calc.input.structure),
            kpoints=calc.input.kpoints,
            potcar=calc.input.potcar,
        )

        doc = cls.from_structure(
            structure=calcs_reversed[0].output.structure,
            meta_structure=calcs_reversed[0].output.structure,
            include_structure=True,
            dir_name=get_uri(dir_name),
            calcs_reversed=calcs_reversed,
            analysis=analysis,
            orig_inputs=orig_inputs,
            completed_at=calcs_reversed[0].completed_at,
            input=InputDoc.from_vasp_calc_doc(calcs_reversed[-1]),
            output=OutputDoc.from_vasp_calc_doc(calcs_reversed[0]),
            state=_get_state(calcs_reversed, analysis),
            run_stats=None,
            vasp_objects={},
            included_objects=[],
            task_type=calcs_reversed[0].task_type,
        )
        if additional_fields:
            doc = doc.copy(update=additional_fields)
        return doc

    @staticmethod
    def get_entry(
        calcs_reversed: List[Calculation], task_id: Optional[str] = None
    ) -> ComputedEntry:
        """
        Get a computed entry from a list of VASP calculation documents.

        Parameters
        ----------
        calcs_reversed
            A list of VASP calculation documents in a reverse order.
        task_id
            The job identifier.

        Returns
        -------
        ComputedEntry
            A computed entry.
        """
        entry_dict = {
            "correction": 0.0,
            "entry_id": task_id,
            "composition": calcs_reversed[0].output.structure.composition,
            "energy": calcs_reversed[0].output.energy,
            "parameters": {
                # Cannot be PotcarSpec document, pymatgen expects a dict
                "potcar_spec": [dict(d) for d in calcs_reversed[0].input.potcar_spec],
                # Required to be compatible with MontyEncoder for the ComputedEntry
                "run_type": str(calcs_reversed[0].run_type),
                "is_hubbard": calcs_reversed[0].input.is_hubbard,
                "hubbards": calcs_reversed[0].input.hubbards,
            },
            "data": {
                "oxide_type": oxide_type(calcs_reversed[0].output.structure),
                "aspherical": calcs_reversed[0].input.parameters.get("LASPH", False),
                "last_updated": str(datetime.utcnow()),
            },
        }
        return ComputedEntry.from_dict(entry_dict)

    @property
    def structure_entry(self) -> ComputedStructureEntry:
        """
        Retrieve a ComputedStructureEntry for this TaskDoc.

        Returns
        -------
        ComputedStructureEntry
            The TaskDoc.entry with corresponding TaskDoc.structure added.
        """
        return ComputedStructureEntry(
            structure=self.structure,
            energy=self.entry.energy,
            correction=self.entry.correction,
            composition=self.entry.composition,
            energy_adjustments=self.entry.energy_adjustments,
            parameters=self.entry.parameters,
            data=self.entry.data,
            entry_id=self.entry.entry_id,
        )


class TrajectoryDoc(BaseModel):
    """
    Model for task trajectory data
    """

    task_id: Optional[str] = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    trajectories: Optional[List[Trajectory]] = Field(
        None,
        description="Trajectory data for calculations associated with a task doc.",
    )


class EntryDoc(BaseModel):
    """
    Model for task entry data
    """

    task_id: Optional[str] = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    entry: Optional[ComputedStructureEntry] = Field(
        None,
        description="Computed structure entry for the calculation associated with the task doc.",
    )


class DeprecationDoc(BaseModel):
    """
    Model for task deprecation data
    """

    task_id: Optional[str] = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    deprecated: Optional[bool] = Field(
        None,
        description="Whether the ID corresponds to a deprecated calculation.",
    )

    deprecation_reason: Optional[str] = Field(
        None,
        description="Reason for deprecation.",
    )


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
        Full URI path, e.g., "fileserver.host.com:/full/path/of/dir_name".
    """
    import socket

    fullpath = Path(dir_name).absolute()
    hostname = socket.gethostname()
    try:
        hostname = socket.gethostbyaddr(hostname)[0]
    except (socket.gaierror, socket.herror):
        pass
    return f"{hostname}:{fullpath}"


def _parse_transformations(
    dir_name: Path,
) -> Tuple[Dict, Optional[int], Optional[List[str]], Optional[str]]:
    """Parse transformations.json file."""
    transformations = {}
    filenames = tuple(dir_name.glob("transformations.json*"))
    icsd_id = None
    if len(filenames) >= 1:
        transformations = loadfn(filenames[0], cls=None)
        try:
            match = re.match(r"(\d+)-ICSD", transformations["history"][0]["source"])
            if match:
                icsd_id = int(match.group(1))
        except (KeyError, IndexError):
            pass

    # We don't want to leave tags or authors in the
    # transformations file because they'd be copied into
    # every structure generated after this one.
    other_parameters = transformations.get("other_parameters", {})
    new_tags = other_parameters.pop("tags", None)
    new_author = other_parameters.pop("author", None)

    if "other_parameters" in transformations and not other_parameters:
        # if dict is now empty remove it
        transformations.pop("other_parameters")

    return transformations, icsd_id, new_tags, new_author


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
    -------
    Optional[dict]
        The information parsed from custodian.json file.
    """
    filenames = tuple(dir_name.glob("custodian.json*"))
    if len(filenames) >= 1:
        return loadfn(filenames[0], cls=None)
    return None


def _parse_orig_inputs(
    dir_name: Path,
) -> Dict[str, Union[Kpoints, Poscar, PotcarSpec, Incar]]:
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
    Dict[str, Union[Kpints, Poscar, PotcarSpec, Incar]]
        The original POSCAR, KPOINTS, POTCAR, and INCAR data.
    """
    orig_inputs = {}
    input_mapping = {
        "INCAR": Incar,
        "KPOINTS": Kpoints,
        "POTCAR": VaspPotcar,
        "POSCAR": Poscar,
    }
    for filename in dir_name.glob("*.orig*"):
        for name, vasp_input in input_mapping.items():
            if f"{name}.orig" in str(filename):
                if name == "POTCAR":
                    # can't serialize POTCAR
                    orig_inputs[name.lower()] = PotcarSpec.from_potcar(
                        vasp_input.from_file(filename)
                    )
                else:
                    orig_inputs[name.lower()] = vasp_input.from_file(filename)

    return orig_inputs


def _parse_additional_json(dir_name: Path) -> Dict[str, Any]:
    """Parse additional json files in the directory."""
    additional_json = {}
    for filename in dir_name.glob("*.json*"):
        key = filename.name.split(".")[0]
        if key not in ("custodian", "transformations"):
            additional_json[key] = loadfn(filename, cls=None)
    return additional_json


def _get_max_force(calc_doc: Calculation) -> Optional[float]:
    """Get max force acting on atoms from a calculation document."""
    forces: Optional[Union[np.ndarray, List]] = calc_doc.output.ionic_steps[-1].forces
    structure = calc_doc.output.structure
    if forces:
        forces = np.array(forces)
        sdyn = structure.site_properties.get("selective_dynamics")
        if sdyn:
            forces[np.logical_not(sdyn)] = 0
        return max(np.linalg.norm(forces, axis=1))
    return None


def _get_drift_warnings(calc_doc: Calculation) -> List[str]:
    """Get warnings of whether the drift on atoms is too large."""
    warnings = []
    if calc_doc.input.parameters.get("NSW", 0) > 0:
        drift = calc_doc.output.outcar.get("drift", [[0, 0, 0]])
        max_drift = max(np.linalg.norm(d) for d in drift)
        ediffg = calc_doc.input.parameters.get("EDIFFG", None)
        max_force = -float(ediffg) if ediffg and float(ediffg) < 0 else np.inf
        if max_drift > max_force:
            warnings.append(
                f"Drift ({drift}) > desired force convergence ({max_force}), structure "
                "likely not converged to desired accuracy."
            )
    return warnings


def _get_state(calcs_reversed: List[Calculation], analysis: AnalysisDoc) -> TaskState:
    """Get state from calculation documents and relaxation analysis."""
    all_calcs_completed = all(
        [c.has_vasp_completed == TaskState.SUCCESS for c in calcs_reversed]
    )
    if len(analysis.errors) == 0 and all_calcs_completed:
        return TaskState.SUCCESS  # type: ignore
    return TaskState.FAILED  # type: ignore


def _get_run_stats(calcs_reversed: List[Calculation]) -> Dict[str, RunStatistics]:
    """Get summary of runtime statistics for each calculation in this task."""
    run_stats = {}
    total = dict(
        average_memory=0.0,
        max_memory=0.0,
        elapsed_time=0.0,
        system_time=0.0,
        user_time=0.0,
        total_time=0.0,
        cores=0,
    )
    for calc_doc in calcs_reversed:
        stats = calc_doc.output.run_stats
        run_stats[calc_doc.task_name] = stats
        total["average_memory"] = max(total["average_memory"], stats.average_memory)
        total["max_memory"] = max(total["max_memory"], stats.max_memory)
        total["cores"] = max(total["cores"], stats.cores)
        total["elapsed_time"] += stats.elapsed_time
        total["system_time"] += stats.system_time
        total["user_time"] += stats.user_time
        total["total_time"] += stats.total_time
    run_stats["overall"] = RunStatistics(**total)
    return run_stats


def _find_vasp_files(
    path: Union[str, Path],
    volumetric_files: Tuple[str, ...] = _VOLUMETRIC_FILES,
) -> Dict[str, Any]:
    """
    Find VASP files in a directory.

    Only files in folders with names matching a task name (or alternatively files
    with the task name as an extension, e.g., vasprun.relax1.xml) will be returned.

    VASP files in the current directory will be given the task name "standard".

    Parameters
    ----------
    path
        Path to a directory to search.
    volumetric_files
        Volumetric files to search for.

    Returns
    -------
    dict[str, Any]
        The filenames of the calculation outputs for each VASP task, given as a ordered
        dictionary of::

            {
                task_name: {
                    "vasprun_file": vasprun_filename,
                    "outcar_file": outcar_filename,
                    "contcar_file": contcar_filename,
                    "volumetric_files": [CHGCAR, LOCPOT, etc]
                    "elph_poscars": [POSCAR.T=300, POSCAR.T=400, etc]
                },
                ...
            }

    """
    task_names = ["precondition"] + [f"relax{i}" for i in range(9)]
    path = Path(path)
    task_files = OrderedDict()

    def _get_task_files(files, suffix=""):
        vasp_files = {}
        vol_files = []
        elph_poscars = []
        for file in files:
            if file.match(f"*vasprun.xml{suffix}*"):
                vasp_files["vasprun_file"] = file
            elif file.match(f"*OUTCAR{suffix}*"):
                vasp_files["outcar_file"] = file
            elif file.match(f"*CONTCAR{suffix}*"):
                vasp_files["contcar_file"] = file
            elif any([file.match(f"*{f}{suffix}*") for f in volumetric_files]):
                vol_files.append(file)
            elif file.match(f"*POSCAR.T=*{suffix}*"):
                elph_poscars.append(file)

        if len(vol_files) > 0:
            # add volumetric files if some were found or other vasp files were found
            vasp_files["volumetric_files"] = vol_files

        if len(elph_poscars) > 0:
            # add elph displaced poscars if they were found or other vasp files found
            vasp_files["elph_poscars"] = elph_poscars

        return vasp_files

    for task_name in task_names:
        subfolder_match = list(path.glob(f"{task_name}/*"))
        suffix_match = list(path.glob(f"*.{task_name}*"))
        if len(subfolder_match) > 0:
            # subfolder match
            task_files[task_name] = _get_task_files(subfolder_match)
        elif len(suffix_match) > 0:
            # try extension schema
            task_files[task_name] = _get_task_files(
                suffix_match, suffix=f".{task_name}"
            )

    if len(task_files) == 0:
        # get any matching file from the root folder
        standard_files = _get_task_files(list(path.glob("*")))
        if len(standard_files) > 0:
            task_files["standard"] = standard_files

    return task_files
