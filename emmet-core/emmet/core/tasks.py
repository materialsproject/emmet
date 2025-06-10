"""Define core schemas for VASP calculations."""
from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Optional,
    TYPE_CHECKING,
)

import numpy as np
from monty.json import MontyDecoder
from monty.serialization import loadfn
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.core.structure import Structure
from pymatgen.core.trajectory import Trajectory
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from pymatgen.io.vasp import Incar, Kpoints, Poscar
from pymatgen.io.vasp import Potcar as VaspPotcar

from emmet.core.common import convert_datetime
from emmet.core.mpid import MPID
from emmet.core.structure import StructureMetadata
from emmet.core.utils import utcnow
from emmet.core.vasp.calc_types import (
    CalcType,
    RunType,
    TaskType,
    calc_type,
    run_type,
    task_type,
)
from emmet.core.vasp.calculation import (
    Calculation,
    CalculationInput,
    PotcarSpec,
    RunStatistics,
    VaspObject,
)
from emmet.core.vasp.task_valid import TaskState
from emmet.core.vasp.utils import discover_and_sort_vasp_files

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing_extensions import Self

monty_decoder = MontyDecoder()
logger = logging.getLogger(__name__)

_VOLUMETRIC_FILES = ("CHGCAR", "LOCPOT", "AECCAR0", "AECCAR1", "AECCAR2")


class Potcar(BaseModel):
    pot_type: Optional[str] = Field(None, description="Pseudo-potential type, e.g. PAW")
    functional: Optional[str] = Field(
        None, description="Functional type use in the calculation."
    )
    symbols: Optional[list[str]] = Field(
        None, description="List of VASP potcar symbols used in the calculation."
    )


class OrigInputs(CalculationInput):
    poscar: Optional[Poscar] = Field(
        None,
        description="Pymatgen object representing the POSCAR file.",
    )

    potcar: Optional[Potcar | VaspPotcar | list[Any]] = Field(
        None,
        description="Pymatgen object representing the POTCAR file.",
    )

    @field_validator("potcar", mode="before")
    @classmethod
    def potcar_ok(cls, v):
        """Check that the POTCAR meets type requirements."""
        if isinstance(v, list):
            return list(v)
        return v

    @field_validator("potcar", mode="after")
    @classmethod
    def parse_potcar(cls, v):
        """Check that potcar attribute is not a pymatgen POTCAR."""
        if isinstance(v, VaspPotcar):
            # The user should not mix potential types, but account for that here
            # Using multiple potential types will be caught in validation
            pot_typ = "_".join(set(p.potential_type for p in v))
            return Potcar(pot_type=pot_typ, functional=v.functional, symbols=v.symbols)
        return v

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OutputDoc(BaseModel):
    structure: Optional[Structure] = Field(
        None,
        title="Output Structure",
        description="Output Structure from the VASP calculation.",
    )

    density: Optional[float] = Field(None, description="Density of in units of g/cc.")
    energy: Optional[float] = Field(None, description="Total Energy in units of eV.")
    forces: Optional[list[list[float]]] = Field(
        None, description="The force on each atom in units of eV/A."
    )
    stress: Optional[list[list[float]]] = Field(
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
            if isinstance(values["structure"], dict):
                values["density"] = values["structure"].get("density", None)
            else:
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
        if calc_doc.output.ionic_steps:
            forces = calc_doc.output.ionic_steps[-1].forces
            stress = calc_doc.output.ionic_steps[-1].stress
        elif trajectory and (ionic_steps := trajectory.frame_properties) is not None:
            forces = ionic_steps[-1].get("forces")
            stress = ionic_steps[-1].get("stress")
        else:
            raise RuntimeError("Unable to find ionic steps.")

        return cls(
            structure=calc_doc.output.structure,
            density=calc_doc.output.structure.density,
            energy=calc_doc.output.energy,
            energy_per_atom=calc_doc.output.energy_per_atom,
            bandgap=calc_doc.output.bandgap,
            forces=forces,
            stress=stress,
        )


class InputDoc(CalculationInput):
    """Light wrapper around `CalculationInput` with a few extra fields.

    pseudo_potentials (Potcar) : summary of the POTCARs used in the calculation
    xc_override (str) : the exchange-correlation functional used if not
        the one specified by POTCAR
    is_lasph (bool) : how the calculation set LASPH (aspherical corrections)
    magnetic_moments (list of floats) : on-site magnetic moments
    """

    pseudo_potentials: Optional[Potcar] = Field(
        None, description="Summary of the pseudo-potentials used in this calculation"
    )

    xc_override: Optional[str] = Field(
        None, description="Exchange-correlation functional used if not the default"
    )
    is_lasph: Optional[bool] = Field(
        None, description="Whether the calculation was run with aspherical corrections"
    )
    magnetic_moments: Optional[list[float]] = Field(
        None, description="Magnetic moments for each atom"
    )

    @field_validator("parameters", mode="after")
    @classmethod
    def parameter_keys_should_not_contain_spaces(cls, parameters: Optional[dict]):
        # A change in VASP introduced whitespace into some parameters,
        # for example `<i type="string" name="GGA    ">PE</I>` was observed in
        # VASP 6.4.3. This will lead to an incorrect return value from RunType.
        # This validator will ensure that any already-parsed documents are fixed.
        if parameters:
            return {k.strip(): v for k, v in parameters.items()}

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
        xc = calc_doc.input.incar.get("GGA") or calc_doc.input.incar.get("METAGGA")
        if xc:
            xc = xc.upper()

        if len(potcar_meta := calc_doc.input.potcar_type[0].split("_")) == 2:
            pot_type, func = potcar_meta
        elif len(potcar_meta) == 1:
            pot_type = potcar_meta[0]
            func = "LDA"

        pps = Potcar(pot_type=pot_type, functional=func, symbols=calc_doc.input.potcar)
        return cls(
            **calc_doc.input.model_dump(),
            pseudo_potentials=pps,
            xc_override=xc,
            is_lasph=calc_doc.input.parameters.get("LASPH", False),
            magnetic_moments=calc_doc.input.parameters.get("MAGMOM"),
        )


class CustodianDoc(BaseModel):
    corrections: Optional[list[Any]] = Field(
        None,
        title="Custodian Corrections",
        description="List of custodian correction data for calculation.",
    )
    job: Optional[Any] = Field(
        None,
        title="Custodian Job Data",
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

    warnings: Optional[list[str]] = Field(
        None,
        title="Calculation Warnings",
        description="Warnings issued after analysis.",
    )

    errors: Optional[list[str]] = Field(
        None,
        title="Calculation Errors",
        description="Errors issued after analysis.",
    )

    @classmethod
    def from_vasp_calc_docs(
        cls,
        calcs_reversed: list[Calculation],
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
    """Calculation-level details about VASP calculations that power Materials Project."""

    tags: list[str] | None = Field(
        [], title="tag", description="Metadata tagged to a given task."
    )
    dir_name: Optional[str] = Field(
        None, description="The directory for this VASP task"
    )

    state: Optional[TaskState] = Field(None, description="State of this calculation")

    calcs_reversed: Optional[list[Calculation]] = Field(
        None,
        title="Calcs reversed data",
        description="Detailed data for each VASP calculation contributing to the task document.",
    )

    structure: Optional[Structure] = Field(
        None, description="Final output structure from the task"
    )

    task_type: Optional[TaskType | CalcType] = Field(
        None, description="The type of calculation."
    )

    run_type: Optional[RunType] = Field(
        None, description="The functional used in the calculation."
    )

    calc_type: Optional[CalcType] = Field(
        None, description="The functional and task type used in the calculation."
    )

    task_id: Optional[MPID | str] = Field(
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

    included_objects: Optional[list[VaspObject]] = Field(
        None, description="List of VASP objects included with this task document"
    )
    vasp_objects: Optional[dict[VaspObject, Any]] = Field(
        None, description="Vasp objects associated with this task"
    )
    entry: Optional[ComputedEntry] = Field(
        None, description="The ComputedEntry from the task doc"
    )

    task_label: Optional[str] = Field(None, description="A description of the task")
    author: Optional[str] = Field(
        None, description="Author extracted from transformations"
    )
    icsd_id: Optional[str | int] = Field(
        None, description="Inorganic Crystal Structure Database id of the structure"
    )
    transformations: Optional[Any] = Field(
        None,
        description="Information on the structural transformations, parsed from a "
        "transformations.json file",
    )
    additional_json: Optional[dict[str, Any]] = Field(
        None, description="Additional json loaded from the calculation directory"
    )

    custodian: Optional[list[CustodianDoc]] = Field(
        None,
        title="Calcs reversed data",
        description="Detailed custodian data for each VASP calculation contributing to the task document.",
    )

    analysis: Optional[AnalysisDoc] = Field(
        None,
        title="Calculation Analysis",
        description="Some analysis of calculation data after collection.",
    )

    last_updated: datetime = Field(
        default_factory=utcnow,
        description="Timestamp for the most recent calculation for this task document",
    )

    completed_at: Optional[datetime] = Field(
        None, description="Timestamp for when this task was completed"
    )

    batch_id: Optional[str] = Field(
        None,
        description="Identifier for this calculation; should provide rough information about the calculation origin and purpose.",
    )

    run_stats: Optional[Mapping[str, RunStatistics]] = Field(
        None,
        description="Summary of runtime statistics for each calculation in this task",
    )

    # Note that private fields are needed because TaskDoc permits extra info
    # added to the model, unlike TaskDocument. Because of this, when pydantic looks up
    # attrs on the model, it searches for them in the model extra dict first, and if it
    # can't find them, throws an AttributeError. It does this before looking to see if the
    # class has that attr defined on it.

    # _structure_entry: Optional[ComputedStructureEntry] = PrivateAttr(None)

    @model_validator(mode="before")
    @classmethod
    def set_model_pre_fields(cls, values: Any) -> Any:
        """Ensure all important model fields are set and refreshed."""

        # Make sure that the datetime field is properly formatted
        # (Unclear when this is not the case, please leave comment if observed)
        values["last_updated"] = convert_datetime(
            cls, values.get("last_updated", utcnow())
        )

        # Ensure batch_id includes only valid characters
        if (batch_id := values.get("batch_id")) is not None:
            invalid_chars = set(
                char
                for char in batch_id
                if (not char.isalnum()) and (char not in {"-", "_"})
            )
            if len(invalid_chars) > 0:
                raise ValueError(
                    f"Invalid characters in batch_id: {' '.join(invalid_chars)}"
                )

        # Always refresh task_type, calc_type, run_type
        # if attributes containing input sets are available.
        # See, e.g. https://github.com/materialsproject/emmet/issues/960
        # where run_type's were set incorrectly in older versions of TaskDoc
        attrs = ["calcs_reversed", "input", "orig_inputs"]
        for icalc, calc in enumerate(values.get("calcs_reversed", [])):
            if isinstance(calc, dict):
                values["calcs_reversed"][icalc] = Calculation(**calc)

        calcs_reversed = values.get("calcs_reversed")

        if any(values.get(attr) is not None for attr in attrs):
            # To determine task and run type, we search for input sets in this order
            # of precedence: calcs_reversed, inputs, orig_inputs
            inp_set = None
            inp_sets_to_check = [values.get("input"), values.get("orig_inputs")]
            if calcs_reversed:
                inp_sets_to_check = [calcs_reversed[0].get("input")] + inp_sets_to_check

            for inp_set in inp_sets_to_check:
                if inp_set is not None:
                    values["task_type"] = task_type(inp_set)
                    break

            # calcs_reversed needed below
            if calcs_reversed:
                values["run_type"] = cls._get_run_type(calcs_reversed)
                if inp_set is not None:
                    values["calc_type"] = cls._get_calc_type(calcs_reversed, inp_set)

        if calcs_reversed:
            # TODO: remove after imposing TaskDoc schema on older tasks in collection
            if final_struct := calcs_reversed[0].output.structure:
                values["structure"] = values.get("structure", final_struct)
                values["entry"] = values.get(
                    "entry", cls.get_entry(calcs_reversed, values.get("task_id"))
                )

        return values

    @classmethod
    def from_directory(
        cls,
        dir_name: Path | str,
        volumetric_files: tuple[str, ...] = _VOLUMETRIC_FILES,
        store_additional_json: bool = True,
        additional_fields: Optional[dict[str, Any]] = None,
        volume_change_warning_tol: float = 0.2,
        task_names: Optional[list[str]] = None,
        **vasp_calculation_kwargs,
    ) -> Self:
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
        task_names
            Naming scheme for multiple calculations in on folder e.g. ["relax1","relax2"].
            Can be subfolder or extension.
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
        task_files = _find_vasp_files(
            dir_name, volumetric_files=volumetric_files, task_names=task_names
        )

        if len(task_files) == 0:
            raise FileNotFoundError("No VASP files found!")

        calcs_reversed = []
        all_vasp_objects = []
        for task_name in sorted(task_files):
            calc_doc, vasp_objects = Calculation.from_vasp_files(
                dir_name, task_name, **task_files[task_name], **vasp_calculation_kwargs
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
        return doc.model_copy(update=additional_fields)

    @classmethod
    def from_vasprun(
        cls,
        path: str | Path,
        additional_fields: Optional[dict[str, Any]] = None,
        volume_change_warning_tol: float = 0.2,
        **vasp_calculation_kwargs,
    ) -> Self:
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
            doc = doc.model_copy(update=additional_fields)
        return doc

    @staticmethod
    def get_entry(
        calcs_reversed: list[Calculation | dict],
        task_id: Optional[MPID | str] = None,
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
        if isinstance(cr := calcs_reversed[0], dict):
            cr = Calculation(**cr)
        calc_inp = cr.input
        calc_out = cr.output

        entry_dict = {
            "correction": 0.0,
            "entry_id": task_id,
            "composition": calc_out.structure.composition,
            "energy": calc_out.energy,
            "parameters": {
                # Cannot be PotcarSpec document, pymatgen expects a dict
                # Note that `potcar_spec` is optional
                "potcar_spec": (
                    [dict(d) for d in calc_inp.potcar_spec]
                    if calc_inp.potcar_spec
                    else []
                ),
                # Required to be compatible with MontyEncoder for the ComputedEntry
                "run_type": str(cr.run_type),
                "is_hubbard": calc_inp.is_hubbard,
                "hubbards": calc_inp.hubbards,
            },
            "data": {
                "oxide_type": oxide_type(calc_out.structure),
                "aspherical": calc_inp.parameters.get("LASPH", False),
                "last_updated": str(utcnow()),
            },
        }
        return ComputedEntry.from_dict(entry_dict)

    @staticmethod
    def _get_calc_type(
        calcs_reversed: list[Calculation | dict], orig_inputs: OrigInputs | dict
    ) -> CalcType:
        """Get the calc type from calcs_reversed.

        Returns
        --------
        CalcType
            The type of calculation.
        """
        if isinstance(calcs_reversed[0], Calculation):
            cr_inp = calcs_reversed[0].input
            params = cr_inp.parameters
            incar = cr_inp.incar
        else:
            cr_inp = calcs_reversed[0].get("input", {})
            params = cr_inp.get("parameters", {})
            incar = cr_inp.get("incar", {})

        inputs = cr_inp if len(calcs_reversed) > 0 else orig_inputs
        return calc_type(inputs, {**params, **incar})

    @staticmethod
    def _get_run_type(calcs_reversed: list[Calculation | dict]) -> RunType:
        """Get the run type from calcs_reversed.

        Returns
        --------
        RunType
            The type of calculation.
        """
        if isinstance(calcs_reversed[0], Calculation):
            params = calcs_reversed[0].input.parameters
            incar = calcs_reversed[0].input.incar
        else:
            cr_inp = calcs_reversed[0].get("input", {})
            params = cr_inp.get("parameters", {})
            incar = cr_inp.get("incar", {})
        return run_type({**params, **incar})

    @property
    def structure_entry(self) -> ComputedStructureEntry:
        """
        Retrieve a ComputedStructureEntry for this TaskDoc.

        Returns
        -------
        ComputedStructureEntry
            The TaskDoc.entry with corresponding TaskDoc.structure added.
        """
        if not self.structure or not self.entry:
            raise ValueError(
                "Need both a `structure` and `entry` to return a `ComputedStructureEntry`."
            )

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
    """Model for task trajectory data."""

    task_id: Optional[str] = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    trajectories: Optional[list[Trajectory]] = Field(
        None,
        description="Trajectory data for calculations associated with a task doc.",
    )


class EntryDoc(BaseModel):
    """Model for task entry data."""

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
    """Model for task deprecation data."""

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
) -> tuple[dict, Optional[int], Optional[list[str]], Optional[str]]:
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


def _parse_custodian(dir_name: Path) -> Optional[dict]:
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
) -> dict[str, Kpoints | Poscar | PotcarSpec | Incar]:
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
    dict[str, Kpoints | Poscar | PotcarSpec | Incar ]
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
                        vasp_input.from_file(filename)  # type: ignore[attr-defined]
                    )
                else:
                    orig_inputs[name.lower()] = vasp_input.from_file(filename)  # type: ignore[attr-defined]

    return orig_inputs


def _parse_additional_json(dir_name: Path) -> dict[str, Any]:
    """Parse additional json files in the directory."""
    additional_json = {}
    for filename in dir_name.glob("*.json*"):
        key = filename.name.split(".")[0]
        # ignore FW.json(.gz) so jobflow doesn't try to parse prev_vasp_dir OutputReferences
        # was causing atomate2 MP workflows to fail with ValueError: Could not resolve reference
        # 7f5a7f14-464c-4a5b-85f9-8d11b595be3b not in store or cache
        # contact @janosh in case of questions
        if key not in ("custodian", "transformations", "FW"):
            additional_json[key] = loadfn(filename, cls=None)
    return additional_json


def _get_max_force(calc_doc: Calculation) -> Optional[float]:
    """Get max force acting on atoms from a calculation document."""
    if calc_doc.output.ionic_steps:
        forces: Optional[np.ndarray | list] = None
        if calc_doc.output.ionic_steps:
            forces = calc_doc.output.ionic_steps[-1].forces

        structure = calc_doc.output.structure
        if forces:
            forces = np.array(forces)
            sdyn = structure.site_properties.get("selective_dynamics")
            if sdyn:
                forces[np.logical_not(sdyn)] = 0
            return max(np.linalg.norm(forces, axis=1))
    return None


def _get_drift_warnings(calc_doc: Calculation) -> list[str]:
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


def _get_state(calcs_reversed: list[Calculation], analysis: AnalysisDoc) -> TaskState:
    """Get state from calculation documents and relaxation analysis."""
    all_calcs_completed = all(
        c.has_vasp_completed == TaskState.SUCCESS for c in calcs_reversed
    )
    if analysis.errors and len(analysis.errors) == 0 and all_calcs_completed:
        return TaskState.SUCCESS  # type: ignore
    return TaskState.FAILED  # type: ignore


def _get_run_stats(calcs_reversed: list[Calculation]) -> dict[str, RunStatistics]:
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
    path: str | Path,
    volumetric_files: Sequence[str] | None = None,
    task_names: Sequence[str] | None = None,
) -> dict[str, dict[str, Path | list[Path]]]:
    """
    Find VASP files in a directory.

    Only files in folders with names matching a task name (or alternatively files
    with the task name as an extension, e.g., vasprun.relax1.xml) will be returned.

    VASP files in the current directory will be given the task name "standard".

    Parameters
    ----------
    path
        Path to a directory to search.
    volumetric_files : sequence of str, defaults to _VOLUMETRIC_FILES
        Volumetric files to search for.
    task_names : sequence of str, defaults to
        task_names = ["precondition","standard","relax0","relax1",..."relax8"]


    Returns
    -------
    dict[str,dict[str,Path | list[Path]]]
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
    base_path = Path(path)
    volumetric_files = volumetric_files or _VOLUMETRIC_FILES
    task_names = task_names or ["precondition"] + [f"relax{i}" for i in range(9)]

    task_files: dict[str, dict[str, Path | list[Path]]] = {}

    def _update_task_files(tpath) -> None:
        for category, files in discover_and_sort_vasp_files(tpath).items():
            for f in files:
                f = f.name
                tasks = sorted([t for t in task_names if t in f])
                task = "standard" if len(tasks) == 0 else tasks[0]
                if task not in task_files:
                    task_files[task] = {}
                if (
                    is_list_like := category in ("volumetric_files", "elph_poscars")
                ) and category not in task_files[task]:
                    task_files[task][category] = []

                abs_f = Path(base_path) / f
                if is_list_like:
                    task_files[task][category].append(abs_f)  # type: ignore[union-attr]
                else:
                    task_files[task][category] = abs_f

    _update_task_files(base_path)

    # TODO: TaskDoc permits matching sub directories if they use one of
    # `task_names` as a directory name.
    # Not sure this is behavior we want to keep in the long term,
    # but is maintained here for backwards compatibility.
    for task_name in task_names:
        if (subdir := base_path / task_name).exists():
            _update_task_files(subdir)

    return task_files
