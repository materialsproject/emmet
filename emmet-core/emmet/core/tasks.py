# mypy: ignore-errors
from __future__ import annotations

import logging
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Type, TypeVar, Union

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

monty_decoder = MontyDecoder()
logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound="TaskDoc")
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

    potcar: Optional[Union[Potcar, VaspPotcar, list[Any]]] = Field(
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
        elif trajectory:
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

        pot_type, func = calc_doc.input.potcar_type[0].split("_")
        func = "lda" if len(pot_type) == 1 else "_".join(func)
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


class EmmetComputedEntry(BaseModel):
    """Fixed-schema version of pymatgen ComputedEntry."""

    energy: float
    composition: dict[str, float]
    entry_id: MPID | None = None
    correction: float | None = None
    energy_adjustments: list[float] | None = None
    potcar_spec: list[PotcarSpec] | None = None
    run_type: RunType | None = None
    is_hubbard: bool = False
    hubbards: dict[str, float] | None = None
    oxide_type: str | None = None
    aspherical: bool = False
    last_updated: datetime | None = None

    def get_computed_entry(self) -> ComputedEntry:
        """Get pymatgen computed entry."""
        return ComputedEntry.from_dict(
            {
                "correction": self.correction,
                "entry_id": self.entry_id,
                "composition": self.composition,
                "energy": self.energy,
                "parameters": {
                    "potcar_spec": (
                        [ps.model_dump() for ps in self.potcar_spec]
                        if self.potcar_spec is not None
                        else []
                    ),
                    "run_type": str(self.run_type),
                    "is_hubbard": self.is_hubbard,
                    "hubbards": self.hubbards,
                },
                "data": {
                    "oxide_type": self.oxide_type,
                    "aspherical": self.aspherical,
                    "last_updated": str(self.last_updated),
                },
            }
        )


class DbTaskDoc(StructureMetadata):
    """Calculation-level details about VASP calculations that power Materials Project.

    This schema is intended to be fixed for database best practices.
    """

    tags: list[str] | None = Field(
        None, title="tag", description="Metadata tagged to a given task."
    )
    dir_name: str | None = Field(None, description="The directory for this VASP task")

    calcs_reversed: list[Calculation] | None = Field(
        None,
        title="Calcs reversed data",
        description="Detailed data for each VASP calculation contributing to the task document.",
    )

    structure: Structure | None = Field(
        None, description="Final output structure from the task"
    )

    task_type: TaskType | None = Field(None, description="The type of calculation.")

    run_type: RunType | None = Field(
        None, description="The functional used in the calculation."
    )

    calc_type: CalcType | None = Field(
        None, description="The functional and task type used in the calculation."
    )

    task_id: MPID | None = Field(
        None,
        description="The (task) ID of this calculation, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    orig_inputs: OrigInputs | None = Field(
        None,
        description="The exact set of input parameters used to generate the current task document.",
    )

    input: InputDoc | None = Field(
        None,
        description="The input structure used to generate the current task document.",
    )

    output: OutputDoc | None = Field(
        None,
        description="The exact set of output parameters used to generate the current task document.",
    )

    included_objects: list[VaspObject] | None = Field(
        None, description="List of VASP objects included with this task document"
    )
    vasp_objects: dict[VaspObject, Any] | None = Field(
        None, description="VASP objects associated with this task"
    )
    entry: EmmetComputedEntry | None = Field(
        None, description="The EmmetComputedEntry from the task doc"
    )

    icsd_id: int | None = Field(
        None, description="Inorganic Crystal Structure Database id of the structure"
    )
    transformations: Any | None = Field(
        None,
        description="Information on the structural transformations, parsed from a "
        "transformations.json file",
    )

    custodian: list[CustodianDoc] | None = Field(
        None,
        title="Calcs reversed data",
        description="Detailed custodian data for each VASP calculation contributing to the task document.",
    )

    analysis: AnalysisDoc | None = Field(
        None,
        title="Calculation Analysis",
        description="Some analysis of calculation data after collection.",
    )

    last_updated: datetime | None = Field(
        utcnow(),
        description="Timestamp for the most recent calculation for this task document",
    )

    completed_at: datetime | None = Field(
        None, description="Timestamp for when this task was completed"
    )

    batch_id: str | None = Field(
        None,
        description="Identifier for this calculation; should provide rough information about the calculation origin and purpose.",
    )

    # Note that private fields are needed because TaskDoc permits extra info
    # added to the model, unlike TaskDocument. Because of this, when pydantic looks up
    # attrs on the model, it searches for them in the model extra dict first, and if it
    # can't find them, throws an AttributeError. It does this before looking to see if the
    # class has that attr defined on it.

    # _structure_entry: Optional[ComputedStructureEntry] = PrivateAttr(None)

    def model_post_init(self, __context: Any) -> None:
        """Ensure that attrs are properly instantiated."""

        self.tags = self.tags or []

        # Always refresh task_type, calc_type, run_type
        # See, e.g. https://github.com/materialsproject/emmet/issues/960
        # where run_type's were set incorrectly in older versions of TaskDoc

        # only run if attributes containing input sets are available
        attrs = ["calcs_reversed", "input", "orig_inputs"]
        if not any(hasattr(self, attr) and getattr(self, attr) for attr in attrs):
            return

        # To determine task and run type, we search for input sets in this order
        # of precedence: calcs_reversed, inputs, orig_inputs
        inp_set = None
        inp_sets_to_check = [self.input, self.orig_inputs]
        if (calcs_reversed := getattr(self, "calcs_reversed", None)) is not None:
            inp_sets_to_check = [calcs_reversed[0].input] + inp_sets_to_check

        for inp_set in inp_sets_to_check:
            if inp_set is not None:
                self.task_type = task_type(inp_set)
                break

        # calcs_reversed needed below
        if calcs_reversed is not None:
            self.run_type = self._get_run_type(calcs_reversed)
            if inp_set is not None:
                self.calc_type = self._get_calc_type(calcs_reversed, inp_set)

            # TODO: remove after imposing TaskDoc schema on older tasks in collection
            if self.structure is None:
                self.structure = calcs_reversed[0].output.structure

        # Set the computed entry if not set
        if (
            not self.entry
            and self.calcs_reversed
            and getattr(self.calcs_reversed[0].output, "structure", None)
        ):
            use_pymatgen_rep = getattr(self, "_use_pymatgen_rep", False)
            self.entry = self.get_entry(
                self.calcs_reversed, self.task_id, use_pymatgen_rep=use_pymatgen_rep
            )

    # Make sure that the datetime field is properly formatted
    # (Unclear when this is not the case, please leave comment if observed)
    @field_validator("last_updated", mode="before")
    @classmethod
    def last_updated_dict_ok(cls, v) -> datetime:
        return convert_datetime(cls, v)

    @field_validator("batch_id", mode="before")
    @classmethod
    def _validate_batch_id(cls, v) -> str:
        if v is not None:
            invalid_chars = set(
                char for char in v if (not char.isalnum()) and (char not in {"-", "_"})
            )
            if len(invalid_chars) > 0:
                raise ValueError(
                    f"Invalid characters in batch_id: {' '.join(invalid_chars)}"
                )
        return v

    @classmethod
    def from_directory(
        cls: Type[_T],
        dir_name: Union[Path, str],
        volumetric_files: tuple[str, ...] = _VOLUMETRIC_FILES,
        additional_fields: Optional[dict[str, Any]] = None,
        volume_change_warning_tol: float = 0.2,
        task_names: Optional[list[str]] = None,
        **vasp_calculation_kwargs,
    ) -> _T:
        """
        Create a task document from a directory containing VASP files.

        Parameters
        ----------
        dir_name
            The path to the folder containing the calculation outputs.
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
        DbTaskDoc
            A fixed-schema task document for the calculation.
        """
        logger.info(f"Getting task doc in: {dir_name}")

        dir_name = Path(dir_name)
        task_files = _find_vasp_files(
            dir_name, volumetric_files=volumetric_files, task_names=task_names
        )

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
            icsd_id=icsd_id,
            tags=tags,
            author=author,
            completed_at=calcs_reversed[0].completed_at,
            input=InputDoc.from_vasp_calc_doc(calcs_reversed[-1]),
            output=OutputDoc.from_vasp_calc_doc(
                calcs_reversed[0],
                vasp_objects.get(VaspObject.TRAJECTORY),  # type: ignore
            ),
            vasp_objects=vasp_objects,
            included_objects=included_objects,
            task_type=calcs_reversed[0].task_type,
        )

        if additional_fields:
            doc = doc.model_copy(update=additional_fields)
        return doc

    @classmethod
    def from_vasprun(
        cls: Type[_T],
        path: Union[str, Path],
        additional_fields: Optional[dict[str, Any]] = None,
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
            vasp_objects={},
            included_objects=[],
            task_type=calcs_reversed[0].task_type,
        )
        if additional_fields:
            doc = doc.model_copy(update=additional_fields)
        return doc

    @staticmethod
    def get_entry(
        calcs_reversed: list[Calculation],
        task_id: Optional[Union[MPID, str]] = None,
        use_pymatgen_rep: bool = False,
    ) -> EmmetComputedEntry | ComputedEntry:
        """
        Get a computed entry from a list of VASP calculation documents.

        Parameters
        ----------
        calcs_reversed
            A list of VASP calculation documents in a reverse order.
        task_id
            The job identifier.
        use_pymatgen_rep
            Whether to use the emmet or pymatgen model of a computed entry.

        Returns
        -------
        ComputedEntry
            A computed entry.
        """
        inp_kwargs = {
            k: getattr(calcs_reversed[0].input, k, None)
            for k in ("potcar_spec", "is_hubbard", "hubbards")
        }
        ce = EmmetComputedEntry(
            energy=calcs_reversed[0].output.energy,
            composition=calcs_reversed[0].output.structure.composition.as_dict(),
            entry_id=task_id,
            correction=0.0,
            run_type=calcs_reversed[0].run_type,
            oxide_type=oxide_type(calcs_reversed[0].output.structure),
            aspherical=calcs_reversed[0].input.parameters.get("LASPH", False),
            last_updated=utcnow(),
            **inp_kwargs,
        )
        if use_pymatgen_rep:
            return ce.get_computed_entry()
        return ce

    @staticmethod
    def _get_calc_type(
        calcs_reversed: list[Calculation], orig_inputs: OrigInputs
    ) -> CalcType:
        """Get the calc type from calcs_reversed.

        Returns
        --------
        CalcType
            The type of calculation.
        """
        inputs = (
            calcs_reversed[0].input.model_dump()
            if len(calcs_reversed) > 0
            else orig_inputs
        )
        params = calcs_reversed[0].input.parameters
        incar = calcs_reversed[0].input.incar
        return calc_type(inputs, {**params, **incar})

    @staticmethod
    def _get_run_type(calcs_reversed: list[Calculation]) -> RunType:
        """Get the run type from calcs_reversed.

        Returns
        --------
        RunType
            The type of calculation.
        """
        params = calcs_reversed[0].input.parameters
        incar = calcs_reversed[0].input.incar
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
        ce = self.entry.get_computed_entry()
        return ComputedStructureEntry(
            structure=self.structure,
            energy=ce.energy,
            correction=ce.correction,
            composition=ce.composition,
            energy_adjustments=ce.energy_adjustments,
            parameters=ce.parameters,
            data=ce.data,
            entry_id=ce.entry_id,
        )


class TaskDoc(DbTaskDoc, extra="allow"):
    """Calculation-level details about VASP calculations that power Materials Project."""

    state: TaskState | None = Field(None, description="State of this calculation")

    task_label: str | None = Field(None, description="A description of the task")
    author: str | None = Field(
        None, description="Author extracted from transformations"
    )

    additional_json: Optional[dict[str, Any]] = Field(
        None, description="Additional json loaded from the calculation directory"
    )

    run_stats: dict[str, RunStatistics] | None = Field(
        None,
        description="Summary of runtime statistics for each calculation in this task",
    )

    entry: ComputedEntry | None = Field(
        None, description="The ComputedEntry from the task doc"
    )

    _use_pymatgen_rep: bool = True

    def model_post_init(self, __context: Any) -> None:
        """Ensure fields are set correctly that are not defined in DbTaskDoc."""
        super().model_post_init(__context)

        if self.calcs_reversed:
            if self.run_stats is None:
                self.run_stats = _get_run_stats(self.calcs_reversed)
            if self.state is None and self.analysis:
                self.state = _get_state(self.calcs_reversed, self.analysis)

    @classmethod
    def from_directory(
        cls: Type[_T],
        dir_name: Union[Path, str],
        volumetric_files: tuple[str, ...] = _VOLUMETRIC_FILES,
        store_additional_json: bool = True,
        additional_fields: Optional[dict[str, Any]] = None,
        volume_change_warning_tol: float = 0.2,
        task_names: Optional[list[str]] = None,
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

        additional_json = None
        if store_additional_json:
            additional_json = _parse_additional_json(Path(dir_name))

        db_task = DbTaskDoc.from_directory(
            dir_name,
            volumetric_files=volumetric_files,
            volume_change_warning_tol=volume_change_warning_tol,
            task_names=task_names,
            **vasp_calculation_kwargs,
        )
        config = db_task.model_dump()
        config["entry"] = db_task.entry.get_computed_entry()
        if additional_json:
            config.update(additional_json=additional_json)

        # NB: additional_fields populated here because they may not be
        # part of the DbTaskDoc model
        if additional_fields:
            config.update(**additional_fields)
        return cls(**config)


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
) -> dict[str, Union[Kpoints, Poscar, PotcarSpec, Incar]]:
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
    dict[str, Union[Kpints, Poscar, PotcarSpec, Incar]]
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
        forces: Optional[Union[np.ndarray, list]] = None
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
    if len(analysis.errors) == 0 and all_calcs_completed:
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
    for calc_doc in [cr for cr in calcs_reversed if cr.output.run_stats]:
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
    volumetric_files: tuple[str, ...] = _VOLUMETRIC_FILES,
    task_names: Optional[list[str]] = None,
) -> dict[str, Any]:
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
            file_no_path = file.relative_to(path)
            if file.match(f"*vasprun.xml{suffix}*"):
                vasp_files["vasprun_file"] = file_no_path
            elif file.match(f"*OUTCAR{suffix}*"):
                vasp_files["outcar_file"] = file_no_path
            elif file.match(f"*CONTCAR{suffix}*"):
                vasp_files["contcar_file"] = file_no_path
            elif any(file.match(f"*{f}{suffix}*") for f in volumetric_files):
                vol_files.append(file_no_path)
            elif file.match(f"*POSCAR.T=*{suffix}*"):
                elph_poscars.append(file_no_path)
            elif file.match(f"*OSZICAR{suffix}*"):
                vasp_files["oszicar_file"] = file_no_path

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
