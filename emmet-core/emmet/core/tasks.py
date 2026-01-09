"""Define core schemas for VASP calculations."""

from __future__ import annotations

import logging
import re
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Annotated

import numpy as np
from monty.json import MontyDecoder
from monty.serialization import loadfn
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    BeforeValidator,
    WrapSerializer,
    model_validator,
)
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.core.trajectory import Trajectory as PmgTrajectory
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from pymatgen.io.vasp import Incar, Kpoints, Poscar

from emmet.core.structure import StructureMetadata
from emmet.core.trajectory import RelaxTrajectory, Trajectory
from emmet.core.types.enums import TaskState, VaspObject
from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    ComputedEntryType,
    ComputedStructureEntryType,
)
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.typing import (
    DateTimeType,
    IdentifierType,
    NullableDateTimeType,
    JsonListType,
    JsonDictType,
    _ser_json_like,
    _deser_json_like,
)
from emmet.core.utils import type_override, utcnow
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
    CoreCalculationOutput,
    PotcarSpec,
    RunStatistics,
    get_trajectories_from_calculations,
)
from emmet.core.vasp.utils import TASK_NAMES, discover_and_sort_vasp_files

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import Self


monty_decoder = MontyDecoder()
logger = logging.getLogger(__name__)

_VOLUMETRIC_FILES = ("CHGCAR", "LOCPOT", "AECCAR0", "AECCAR1", "AECCAR2")


class OrigInputs(CalculationInput):
    """Maintained for backward compatibility - deprecated."""

    def model_post_init(self, __context):
        super().model_post_init(__context)
        warnings.warn(
            f"The `{self.__class__.__name__}` class has been marked "
            "for deprecation to ensure parity of the inputs field "
            "in `TaskDoc`. Please transition to using `CalculationInput`, "
            f"which is fully backwards compatible with `{self.__class__.__name__}`.",
            stacklevel=2,
        )


class InputDoc(OrigInputs):
    """Maintained for backward compatibility - deprecated."""


class OutputDoc(BaseModel):
    structure: StructureType | None = Field(
        None,
        title="Output Structure",
        description="Output Structure from the VASP calculation.",
    )

    density: float | None = Field(None, description="Density of in units of g/cc.")
    energy: float | None = Field(None, description="Total Energy in units of eV.")
    forces: list[list[float]] | None = Field(
        None, description="The force on each atom in units of eV/A."
    )
    stress: list[list[float]] | None = Field(
        None, description="The stress on the cell in units of kB."
    )
    energy_per_atom: float | None = Field(
        None, description="The final DFT energy per atom for the last calculation"
    )
    bandgap: float | None = Field(
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
        cls,
        calc_doc: Calculation,
        trajectory: RelaxTrajectory | PmgTrajectory | None = None,
    ) -> "OutputDoc":
        """
        Create a summary of VASP calculation outputs from a VASP calculation document.

        This will first look for ionic steps in the calculation document.
        If found, will use it and ignore the trajectory.
        If not, will get ionic steps from the trajectory.

        Parameters
        ----------
        calc_doc
            A VASP calculation document.
        trajectory
            An emmet-core Trajectory.

        Returns
        -------
        OutputDoc
            The calculation output summary.
        """
        forces = None
        stress = None
        if calc_doc.output.ionic_steps:
            forces = calc_doc.output.ionic_steps[-1].forces
            stress = calc_doc.output.ionic_steps[-1].stress
        elif trajectory:
            if isinstance(trajectory, PmgTrajectory):
                forces = trajectory.frame_properties[-1]["forces"]  # type: ignore[index]
                stress = trajectory.frame_properties[-1]["stress"]  # type: ignore[index]
            else:
                forces = trajectory.forces[-1]
                stress = trajectory.stress[-1]
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


@type_override({"corrections": str, "job": str})
class CustodianDoc(BaseModel):
    corrections: JsonListType = Field(
        None,
        title="Custodian Corrections",
        description="List of custodian correction data for calculation.",
    )
    job: JsonDictType = Field(
        None,
        title="Custodian Job Data",
        description="Job data logged by custodian.",
    )


class AnalysisDoc(BaseModel):
    delta_volume: float | None = Field(
        None,
        title="Volume Change",
        description="Volume change for the calculation.",
    )
    delta_volume_percent: float | None = Field(
        None,
        title="Volume Change Percent",
        description="Percent volume change for the calculation.",
    )
    max_force: float | None = Field(
        None,
        title="Max Force",
        description="Maximum force on any atom at the end of the calculation.",
    )

    warnings: list[str] | None = Field(
        None,
        title="Calculation Warnings",
        description="Warnings issued after analysis.",
    )

    errors: list[str] | None = Field(
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


@type_override({"transformations": str, "vasp_objects": str})
class CoreTaskDoc(StructureMetadata):
    """Calculation-level details about VASP calculations that power the Materials Project."""

    batch_id: str | None = Field(
        None,
        description="Identifier for this calculation; should provide rough information about the calculation origin and purpose.",
    )
    calc_type: CalcType | None = Field(
        None, description="The functional and task type used in the calculation."
    )
    completed_at: NullableDateTimeType = Field(
        description="Timestamp for when this task was completed"
    )
    dir_name: str | None = Field(None, description="The directory for this VASP task")
    icsd_id: int | None = Field(
        None, description="Inorganic Crystal Structure Database id of the structure"
    )
    input: CalculationInput | None = Field(
        None,
        description="VASP calculation inputs",
    )
    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent calculation for this task document",
    )
    orig_inputs: CalculationInput | None = Field(
        None,
        description="The exact set of input parameters used to generate the current task document.",
    )
    output: CoreCalculationOutput | None = Field(
        None,
        description="VASP calculation outputs.",
    )
    run_type: RunType | None = Field(
        None, description="The functional used in the calculation."
    )
    structure: StructureType | None = Field(
        None, description="Final output structure from the task"
    )
    tags: list[str] | None = Field(
        None, title="tag", description="Metadata tagged to a given task."
    )
    task_id: IdentifierType | None = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )
    task_type: TaskType | CalcType | None = Field(
        None, description="The type of calculation."
    )
    transformations: JsonDictType = Field(
        None,
        description="Information on the structural transformations, parsed from a "
        "transformations.json file",
    )
    vasp_objects: Annotated[
        dict[VaspObject, Any] | None,
        BeforeValidator(_deser_json_like),
        WrapSerializer(_ser_json_like),
    ] = Field(None, description="Vasp objects associated with this task")

    @field_validator("batch_id", mode="before")
    def validate_batch_id(cls, batch_id: str):
        if batch_id:
            invalid_chars = set(
                char
                for char in batch_id
                if (not char.isalnum()) and (char not in {"-", "_"})
            )
            if invalid_chars:
                raise ValueError(
                    f"Invalid characters in batch_id: {' '.join(invalid_chars)}"
                )
        return batch_id

    @classmethod
    def from_directory(
        cls,
        dir_name: Path | str,
        volumetric_files: tuple[str, ...] = _VOLUMETRIC_FILES,
        **vasp_calculation_kwargs,
    ) -> tuple[Self, RelaxTrajectory]:
        """
        Create a CoreTaskDoc and corresponding CoreTrajectory from a
        directory containing VASP files.

        Only parses a single calculation. Use TaskDoc.from_directory(...)
        to parse multiple calculations.

        Parameters
        ----------
        dir_name
            The path to the folder containing the calculation outputs.
        volumetric_files
            Volumetric files to search for.
        **vasp_calculation_kwargs
            Additional parsing options that will be passed to the
            :obj:`.Calculation.from_vasp_files` function.

        Returns
        -------
        CoreTaskDoc
            A slim task document for the calculation.
        RelaxTrajectory
            A low memory document for the calculation's trajectory.
        """
        dir_name = Path(dir_name)
        task_files = _find_vasp_files(dir_name, volumetric_files=volumetric_files)

        calc_doc, vasp_objects = Calculation.from_vasp_files(
            dir_name, "standard", **task_files["standard"], **vasp_calculation_kwargs
        )
        transformations, icsd_id, tags, author = _parse_transformations(dir_name)
        task_doc = cls.from_structure(
            calc_type=calc_doc.calc_type,
            completed_at=calc_doc.completed_at,
            dir_name=get_uri(dir_name),
            icsd_id=icsd_id,
            input=calc_doc.input,
            meta_structure=calc_doc.output.structure,
            orig_inputs=_parse_orig_inputs(dir_name),
            output=CoreCalculationOutput(
                **calc_doc.output.model_dump(
                    include=set(CoreCalculationOutput.model_fields)
                )
            ),
            run_type=calc_doc.run_type,
            structure=calc_doc.output.structure,
            tags=tags,
            task_type=calc_doc.task_type,
            transformations=transformations,
            vasp_objects=vasp_objects,
        )

        trajectory = get_trajectories_from_calculations([calc_doc])[0]

        return (task_doc, trajectory)


@type_override({"additional_json": str})
class TaskDoc(CoreTaskDoc, extra="allow"):
    """Flexible wrapper around CoreTaskDoc"""

    additional_json: JsonDictType = Field(
        None, description="Additional json loaded from the calculation directory"
    )
    analysis: AnalysisDoc | None = Field(
        None,
        title="Calculation Analysis",
        description="Some analysis of calculation data after collection.",
    )
    author: str | None = Field(
        None, description="Author extracted from transformations"
    )
    calcs_reversed: list[Calculation] | None = Field(
        None,
        title="Calcs reversed data",
        description="Detailed data for each VASP calculation contributing to the task document.",
    )
    custodian: list[CustodianDoc] | None = Field(
        None,
        title="Calcs reversed data",
        description="Detailed custodian data for each VASP calculation contributing to the task document.",
    )
    entry: ComputedEntryType | None = Field(
        None, description="The ComputedEntry from the task doc"
    )
    included_objects: list[VaspObject] | None = Field(
        None, description="List of VASP objects included with this task document"
    )

    output: OutputDoc | None = Field(
        None,
        description="The exact set of output parameters used to generate the current task document.",
    )
    run_stats: dict[str, RunStatistics] | None = Field(
        None,
        description="Summary of runtime statistics for each calculation in this task",
    )
    state: TaskState | None = Field(None, description="State of this calculation")
    task_label: str | None = Field(None, description="A description of the task")

    @model_validator(mode="before")
    @classmethod
    def set_model_pre_fields(cls, values: Any) -> Any:
        """Ensure all important model fields are set and refreshed."""

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
        additional_fields: dict[str, Any] | None = None,
        volume_change_warning_tol: float = 0.2,
        task_names: list[str] | None = None,
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
        dir_name = Path(dir_name).resolve()
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
            input=calcs_reversed[-1].input,
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
        additional_fields: dict[str, Any] | None = None,
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
        additional_fields: dict[str, Any] = None,
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
        orig_inputs = CalculationInput(
            incar=calc.input.incar,
            structure=calc.input.structure,
            kpoints=calc.input.kpoints,
            potcar=calc.input.potcar,
        )

        doc = cls.from_structure(
            structure=calcs_reversed[0].output.structure,
            meta_structure=calcs_reversed[0].output.structure,
            dir_name=get_uri(dir_name),
            calcs_reversed=calcs_reversed,
            analysis=analysis,
            orig_inputs=orig_inputs,
            completed_at=calcs_reversed[0].completed_at,
            input=calcs_reversed[-1].input,
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
        task_id: IdentifierType | str | int | None = None,
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
        calcs_reversed: list[Calculation], orig_inputs: CalculationInput
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

    @property
    def trajectories(self) -> list[Trajectory] | None:
        """Get Trajectory objects representing calcs_reversed.

        Note that the Trajectory objects represent the proper
        calculation order, not the reversed.

        Thus the first Trajectory represents the first calculation
        that was performed (`self.calcs_reversed[-1]`).
        """
        if self.calcs_reversed:
            return get_trajectories_from_calculations(
                self.calcs_reversed[::-1],
                separate=False,
                identifier=str(self.task_id) if self.task_id else None,
            )
        return None


class TrajectoryDoc(BaseModel):
    """Model for task trajectory data."""

    task_id: str | None = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    trajectories: list[RelaxTrajectory] | None = Field(
        None,
        description="Trajectory data for calculations associated with a task doc.",
    )


class EntryDoc(BaseModel):
    """Model for task entry data."""

    task_id: str | None = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    entry: ComputedStructureEntryType | None = Field(
        None,
        description="Computed structure entry for the calculation associated with the task doc.",
    )


class DeprecationDoc(BaseModel):
    """Model for task deprecation data."""

    task_id: str | None = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    deprecated: bool | None = Field(
        None,
        description="Whether the ID corresponds to a deprecated calculation.",
    )

    deprecation_reason: str | None = Field(
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
) -> tuple[dict, int | None, list[str] | None, str | None]:
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
    -------
    dict | None
        The information parsed from custodian.json file.
    """
    filenames = tuple(dir_name.glob("custodian.json*"))
    if len(filenames) >= 1:
        return loadfn(filenames[0], cls=None)
    return None


def _parse_orig_inputs(
    dir_name: Path, suffix: str | None = ".orig"
) -> dict[str, Kpoints | Poscar | PotcarSpec | Incar]:
    """
    Parse original input files.

    Calculations using custodian generate a *.orig file for the inputs. This is useful
    to know how the calculation originally started.

    Parameters
    ----------
    dir_name
        Path to calculation directory.
    suffix : str or None = ".orig"
        The suffix of the original input files to use.

    Returns
    -------
    dict[str, Kpoints | Poscar | PotcarSpec | Incar ]
        The original POSCAR, KPOINTS, POTCAR, and INCAR data.
    """
    orig_inputs = {}
    input_mapping: dict[str, Kpoints | Poscar | PotcarSpec | Incar] = {
        "INCAR": Incar,
        "KPOINTS": Kpoints,
        "POTCAR": PotcarSpec,
        "POSCAR": Poscar,
    }
    suffix = suffix or ""
    for filename in dir_name.glob("*".join(f"{suffix}.".split("."))):
        if f"POTCAR.spec{suffix}" in str(filename):
            try:
                orig_inputs["potcar_spec"] = PotcarSpec.from_file(filename)
            except Exception:
                # Can't parse non emmet-core style POTCAR.spec files
                continue
        for name, vasp_input in input_mapping.items():
            if f"{name}{suffix}" in str(filename):
                file_suffix = "_spec" if name == "POTCAR" else ""
                orig_inputs[f"{name.lower()}{file_suffix}"] = vasp_input.from_file(
                    filename
                )

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


def _get_max_force(calc_doc: Calculation) -> float | None:
    """Get max force acting on atoms from a calculation document."""
    if calc_doc.output.ionic_steps:
        forces: np.ndarray | list | None = None
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
        max_drift = max(np.linalg.norm(d) for d in drift)  # type: ignore[type-var]
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
    if (
        analysis.errors is None
        or (isinstance(analysis.errors, list) and len(analysis.errors) == 0)
    ) and all_calcs_completed:
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
                    "potcar_spec_file": potcar_spec_filename,
                    "volumetric_files": [CHGCAR, LOCPOT, etc]
                    "elph_poscars": [POSCAR.T=300, POSCAR.T=400, etc]
                },
                ...
            }
    """
    base_path = Path(path)
    volumetric_files = volumetric_files or _VOLUMETRIC_FILES
    task_names = task_names or TASK_NAMES

    task_files: dict[str, dict[str, Path | list[Path]]] = discover_and_sort_vasp_files(
        base_path
    )
    # TODO: TaskDoc permits matching sub directories if they use one of
    # `task_names` as a directory name.
    # Not sure this is behavior we want to keep in the long term,
    # but is maintained here for backwards compatibility.
    for task_name in set(task_names).difference(task_files):
        if (subdir := base_path / task_name).exists():
            for task_name, calcs in discover_and_sort_vasp_files(subdir).items():
                task_files[task_name].update(calcs)

    # For old double-relax style jobs, there will only be one POTCAR/.spec/.orig file
    # even though there will be an INCAR.relax1, INCAR.relax2, etc.
    # Undo that mapping here
    if any(k.startswith("relax") for k in task_files) and task_files.get(
        "standard", {}
    ).get("potcar_spec_file"):
        psf = task_files["standard"].pop("potcar_spec_file")
        for task_name in {k for k in task_files if k.startswith("relax")}:
            task_files[task_name]["potcar_spec_file"] = psf

        if not all(
            task_files.get("standard", {}).get(k)
            for k in (
                "vasprun_file",
                "outcar_file",
                "contcar_file",
            )
        ):
            _ = task_files.pop("standard")

    return task_files
