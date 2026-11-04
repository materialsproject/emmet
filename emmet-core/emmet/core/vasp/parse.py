"""Parse a single VASP calculation into the rows of the parsed-tier tables.

The calculation is parsed once, and produces:

- A `CoreTaskDoc` and a trajectory, which are small and are always made.
- A manifest row, recording what came of the parsing.
- Rows of large objects, according to a `ParsePolicy`: a density of states,
    a band structure, and volumetric data. These are made one at a time by
    `ParsedCalculation.objects`, so that only one is in memory at once. That
    is the only way to parse the volumetric data of a calculation on a machine
    which cannot hold all of it.

Where the calculation comes from is the business of a `CalculationSource`. It
supplies the files of the calculation, and the provenance values
which must not be guessed from the files: where the calculation was found, and
when it was completed. A source for directories is included.

Nothing is written: that is up to the driver, which iterates through the rows.
The tables the rows belong to are described in `emmet.core.vasp.parsed`.

>>> sources = DirectorySource.from_directory("launcher_1")
>>> for source, identifier in zip(sources, new_identifiers):
...     parsed = parse_calculation(source, identifier)
...     write(parsed.task, parsed.trajectory)
...     for table, row in parsed.objects():
...         write(table, row)
...     write("manifest", parsed.manifest_row())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from emmet.core.tasks import (
    CoreTaskDoc,
    _parse_orig_input_files,
    _parse_transformations_file,
    get_uri,
)
from emmet.core.types.enums import StoreTrajectoryOption, TaskState
from emmet.core.types.typing import IdentifierType
from emmet.core.band_theory import BSPathType
from emmet.core.vasp.calc_types.enums import TaskType
from emmet.core.vasp.calculation import (
    Calculation,
    _parse_bandstructure_file,
    get_trajectories_from_calculations,
)
from emmet.core.vasp.models import VOLUMETRIC_PARSERS
from emmet.core.vasp.parsed import (
    BandStructureRow,
    DosRow,
    ManifestRow,
    ParsedRowHeader,
    ParseOutcome,
    VolumetricRow,
    split_band_structure_row,
    split_dos_row,
    volumetric_table_name,
)
from emmet.core.vasp.utils import (
    DEFAULT_CALC_SUFFIXES,
    STANDARD_CALC_SUFFIX,
    CalculationFiles,
    CalculationLocator,
    discover_calculations,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path
    from typing import Any

    from emmet.core.io.pymatgen import Vasprun
    from emmet.core.trajectory import RelaxTrajectory

logger = logging.getLogger(__name__)

_IDENTIFIER_ADAPTER: TypeAdapter[str] = TypeAdapter(IdentifierType)

_ELECTRONIC_STRUCTURE_TASK_TYPES = (
    TaskType.Static,
    TaskType.NSCF_Uniform,
    TaskType.NSCF_Line,
    TaskType.SCF_Line,
)


NOT_PARSED_BY_DEFAULT_VOLUMETRIC_TYPES: dict[str, str] = {
    "CHG": "it holds the same charge density as the CHGCAR, at a lower precision "
    "and without the augmentation data",
    "POT": "it is written to restart optimized-effective-potential calculations "
    "(LVTOT = True), and the local potential is in the LOCPOT",
}
"""The types of volumetric file which are not parsed by default, and why."""

DEFAULT_VOLUMETRIC_TYPES: tuple[str, ...] = tuple(
    file_type
    for file_type in VOLUMETRIC_PARSERS
    if file_type not in NOT_PARSED_BY_DEFAULT_VOLUMETRIC_TYPES
)
"""The types of volumetric file which are parsed by default: all except CHG and POT.

See `NOT_PARSED_BY_DEFAULT_VOLUMETRIC_TYPES` for the reasons. These files can still
be parsed by asking for them: `ParsePolicy(volumetric_types=(..., "CHG", "POT"))`.
"""


class ParsePolicy(BaseModel):
    """Which of the large objects of a calculation to parse.

    The default is the policy of the Materials Project production pipeline,
    which is `MP_PRODUCTION`:

    - Every kind of volumetric data except CHG and POT is kept, whatever the type of
        the calculation. A CHG file is the CHGCAR's charge density at a lower precision
        and without augmentation data, and a POT file is a restart file for
        optimized-effective-potential calculations: the local potential is in the LOCPOT.
    - A density of states and a band structure are only kept for static,
        non-self-consistent (uniform or line mode) and self-consistent line mode
        calculations. The last are the meta-GGA and hybrid calculations whose
        k-points are a weighted mesh followed by a path of zero-weight k-points.
        The raw data of the other calculations has them, for those who want them.
    - Calculations which VASP did not complete or converge, or whose type
        is unknown, have no large objects, but are still recorded.

    Other users can change any of these.
    """

    volumetric_types: tuple[str, ...] | None = Field(
        DEFAULT_VOLUMETRIC_TYPES,
        description="The types of volumetric file to keep, e.g., (CHGCAR, LOCPOT). "
        "By default all of them except CHG and POT. All of them, including those, if "
        "None, and none if empty.",
    )
    dos_task_types: tuple[TaskType, ...] | None = Field(
        _ELECTRONIC_STRUCTURE_TASK_TYPES,
        description="The types of calculation to keep the density of states of. "
        "All of them if None, and none if empty.",
    )
    bandstructure_task_types: tuple[TaskType, ...] | None = Field(
        _ELECTRONIC_STRUCTURE_TASK_TYPES,
        description="The types of calculation to keep the band structure of. "
        "All of them if None, and none if empty.",
    )
    dos_projections: bool = Field(
        True, description="Whether to keep the projections of densities of states."
    )
    bandstructure_projections: bool = Field(
        True, description="Whether to keep the projections of band structures."
    )
    include_failed: bool = Field(
        False,
        description="Whether to parse the large objects of calculations that VASP "
        "did not complete or converge. These are expensive, and a failed calculation "
        "is unlikely to be of use, but the calculation is recorded either way.",
    )
    require_known_task_type: bool = Field(
        True,
        description="Whether to skip the large objects of calculations whose "
        "type could not be identified.",
    )
    average_locpot: bool = Field(
        True,
        description="Whether the task keeps the averages of the LOCPOT along the "
        "axes of the crystal. This reads the LOCPOT once, and reading it again "
        "to keep the LOCPOT as an object is not avoided.",
    )

    @field_validator("volumetric_types", mode="before")
    @classmethod
    def _check_volumetric_types(cls, value: Any) -> Any:
        if value is None:
            return None
        types = tuple(str(v).upper() for v in value)
        if unknown := set(types).difference(VOLUMETRIC_PARSERS):
            raise ValueError(
                f"Unknown volumetric file types {sorted(unknown)}, "
                f"known types are {sorted(VOLUMETRIC_PARSERS)}."
            )
        return types

    def wants_volumetric(self, file_type: str) -> bool:
        """Whether to keep volumetric files of this type, e.g., CHGCAR."""
        return self.volumetric_types is None or file_type in self.volumetric_types

    def wants_dos(self, task_type: TaskType | None) -> bool:
        """Whether to keep the density of states of this type of calculation."""
        return self.dos_task_types is None or task_type in self.dos_task_types

    def wants_bandstructure(self, task_type: TaskType | None) -> bool:
        """Whether to keep the band structure of this type of calculation."""
        return (
            self.bandstructure_task_types is None
            or task_type in self.bandstructure_task_types
        )

    def outcome(self, calc_doc: Calculation) -> ParseOutcome:
        """Decide what to do with the large objects of a parsed calculation."""
        if not self.include_failed and calc_doc.has_vasp_completed != TaskState.SUCCESS:
            return ParseOutcome.SKIPPED_FAILED  # type: ignore[return-value]
        if self.require_known_task_type and calc_doc.task_type == TaskType.Unrecognized:
            return ParseOutcome.SKIPPED_UNRECOGNIZED  # type: ignore[return-value]
        return ParseOutcome.PARSED  # type: ignore[return-value]


MP_PRODUCTION = ParsePolicy()
"""The policy of the Materials Project production pipeline."""


class CalculationSource(Protocol):
    """Where a calculation comes from.

    Besides the files, a source provides what describes the calculation's origin and
    cannot be inferred from the files themselves. For example, the modification
    time of a file does not survive archiving, so a source which reads archives
    must supply the completion time which was recorded when they were made.
    """

    @property
    def files(self) -> CalculationFiles:
        """The files of the calculation, which must exist for as long as it is parsed."""

    @property
    def dir_name(self) -> str:
        """Where the calculation came from, e.g., the output of `get_uri`."""

    @property
    def calc_suffix(self) -> str:
        """The suffix of the calculation in its directory, or standard."""

    @property
    def completed_at(self) -> datetime:
        """When the calculation was completed, as a timezone-aware datetime."""


@dataclass
class DirectorySource:
    """A calculation in a directory."""

    calculation_files: CalculationFiles
    locator: CalculationLocator

    @property
    def files(self) -> CalculationFiles:
        return self.calculation_files

    @property
    def dir_name(self) -> str:
        return get_uri(self.locator.path)

    @property
    def calc_suffix(self) -> str:
        return self.locator.modifier or STANDARD_CALC_SUFFIX

    @property
    def completed_at(self) -> datetime:
        """The modification time of the vasprun.xml, in UTC."""
        vasprun = self.files.vasprun
        if vasprun is None:
            raise FileNotFoundError(f"No vasprun.xml found for {self.locator}")
        return datetime.fromtimestamp(vasprun.stat().st_mtime, tz=UTC)

    @classmethod
    def from_directory(
        cls,
        dir_name: Path | str,
        suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
    ) -> list[DirectorySource]:
        """Find the calculations of a directory, in the order they were run.

        Parameters
        -----------
        dir_name : Path or str
            The directory, which can have any of the layouts supported by
            `emmet.core.vasp.utils.discover_calculations`.
        suffixes : sequence of str
            The suffixes of the calculations, in the order they were run.
        """
        return [
            cls(calculation_files=files, locator=locator)
            for locator, files in discover_calculations(dir_name, suffixes).items()
        ]


@dataclass
class _BandStructureInput:
    """What is needed to read the band structure of a calculation from its files.

    The band structure is read from the file again, so that the Vasprun, which can be
    large, can be freed first.
    """

    vasprun_file: Path
    incar: dict[str, Any]
    kpoints_file: Path | None
    task_type: TaskType


_LINE_TASK_TYPES = (TaskType.NSCF_Line, TaskType.SCF_Line)
"""Calculations whose band structure is along a path of k-points."""

_MESH_TASK_TYPES = (TaskType.Static, TaskType.NSCF_Uniform)
"""Calculations whose band structure is on a uniform mesh of k-points."""


@dataclass
class ParsedCalculation:
    """The result of parsing a calculation. See `parse_calculation`.

    `task` and `trajectory` are None if the calculation could not be read. Everything
    else about the calculation is then in the manifest.
    """

    identifier: str
    outcome: ParseOutcome
    dir_name: str
    calc_suffix: str
    completed_at: datetime | None
    task: CoreTaskDoc | None = None
    trajectory: RelaxTrajectory | None = None
    header: ParsedRowHeader | None = None
    errors: list[str] = field(default_factory=list)
    exception: Exception | None = None

    _policy: ParsePolicy = field(default_factory=ParsePolicy, repr=False)
    _files: CalculationFiles | None = field(default=None, repr=False)
    _vasprun: Vasprun | None = field(default=None, repr=False)
    _bandstructure_input: _BandStructureInput | None = field(default=None, repr=False)
    _tables: list[str] = field(default_factory=list, repr=False)
    _started: bool = field(default=False, repr=False)

    @property
    def _header_kwargs(self) -> dict[str, Any]:
        assert self.header is not None
        return {
            name: getattr(self.header, name)
            for name in (
                "identifier",
                "completed_at",
                "run_type",
                "task_type",
                "formula_pretty",
                "chemsys",
            )
        }

    def _record_error(self, what: str, exc: Exception) -> None:
        message = f"Could not parse {what}: {type(exc).__name__}: {exc}"
        logger.warning(f"{self.identifier} ({self.dir_name}): {message}")
        self.errors.append(message)

    def objects(self) -> Iterator[tuple[str, BaseModel]]:
        """Parse the large objects of the calculation, one row at a time.

        Each row is made when it is asked for, and is not held by the generator
        after it is yielded, so when the consumer releases it its memory is free again.
        Rows come in order of the memory they need: the density of states, then
        the band structure, then each volumetric file.

        An object which cannot be parsed is recorded in `errors`, and the
        rest are not affected. Nothing is yielded if the policy skips the
        calculation's objects.

        The calculation can only be iterated through once.

        Yields
        -----------
        tuple of str and BaseModel
            The name of the table in `emmet.core.vasp.parsed.PARSED_TABLES`
            and the row to add to it.
        """
        if self._started:
            raise RuntimeError("The objects of a calculation can only be parsed once.")
        self._started = True

        vasprun, self._vasprun = self._vasprun, None
        bandstructure_input, self._bandstructure_input = (
            self._bandstructure_input,
            None,
        )
        files, policy = self._files, self._policy
        if self.outcome != ParseOutcome.PARSED or self.header is None or files is None:
            return
        header_kwargs = self._header_kwargs

        if vasprun is not None:
            dos_rows: tuple[Any, Any] | None = None
            try:
                dos = DosRow.from_pmg(vasprun.complete_dos, **header_kwargs)  # type: ignore[arg-type]
                dos_rows = split_dos_row(dos)
            except Exception as exc:
                self._record_error("the density of states", exc)
            del vasprun
            if dos_rows is not None:
                total_dos, projections = dos_rows
                del dos_rows
                yield self._yielded("total-dos", total_dos)
                if projections is not None and policy.dos_projections:
                    yield self._yielded("projected-dos", projections)
                del total_dos, projections

        if bandstructure_input is not None:
            bs_rows: tuple[Any, Any] | None = None
            try:
                is_line = bandstructure_input.task_type in _LINE_TASK_TYPES
                pmg_bs = _parse_bandstructure_file(
                    "auto",
                    bandstructure_input.vasprun_file,
                    bandstructure_input.incar,
                    use_emmet_models=False,
                    kpoints_file=bandstructure_input.kpoints_file,
                    # The band structure of a line calculation is along its path. An
                    # NSCF one can be read as a band structure on its k-points if that
                    # fails, as is done for TaskDoc. A self-consistent one cannot: its
                    # k-points are a mesh and then the path, so that is not its band
                    # structure, and an exception is raised.
                    line_mode=True if is_line else None,
                    strict_line_mode=(
                        bandstructure_input.task_type == TaskType.SCF_Line
                    ),
                )
                if pmg_bs is not None:
                    # A band structure on a mesh has no path convention, which is
                    # not the same as not knowing it
                    path_kwargs = (
                        {"path_convention": BSPathType.uniform}
                        if bandstructure_input.task_type in _MESH_TASK_TYPES
                        else {}
                    )
                    bs_rows = split_band_structure_row(
                        BandStructureRow.from_pmg(
                            pmg_bs,
                            **path_kwargs,
                            **header_kwargs,  # type: ignore[arg-type]
                        )
                    )
                    del pmg_bs
            except Exception as exc:
                self._record_error("the band structure", exc)
            if bs_rows is not None:
                bandstructure, projections = bs_rows
                del bs_rows
                yield self._yielded("bandstructures", bandstructure)
                if projections is not None and policy.bandstructure_projections:
                    yield self._yielded("projected-bandstructures", projections)
                del bandstructure, projections

        for file_type, path in files.volumetric.items():
            if not policy.wants_volumetric(file_type):
                continue
            table = volumetric_table_name(path.name)
            try:
                pmg_vol = VOLUMETRIC_PARSERS[file_type].from_file(str(path))
                volumetric = VolumetricRow.from_pmg(
                    pmg_vol,
                    file_name=path.name,
                    **header_kwargs,  # type: ignore[arg-type]
                )
                del pmg_vol
            except Exception as exc:
                self._record_error(path.name, exc)
                continue
            assert table is not None
            yield self._yielded(table, volumetric)
            del volumetric

    def _yielded(self, table: str, row: BaseModel) -> tuple[str, BaseModel]:
        if table not in self._tables:
            self._tables.append(table)
        return table, row

    def manifest_row(self) -> ManifestRow:
        """The manifest row of the calculation.

        This is complete once all of `objects()` has been consumed: until then
        it does not list all of the tables the calculation has rows in, or errors.
        """
        return ManifestRow(
            identifier=self.identifier,
            dir_name=self.dir_name,
            calc_suffix=self.calc_suffix,
            completed_at=self.completed_at,
            outcome=self.outcome,
            run_type=self.header.run_type if self.header else None,
            task_type=self.header.task_type if self.header else None,
            tables=list(self._tables),
            errors=list(self.errors),
        )


def parse_calculation(
    source: CalculationSource,
    identifier: str,
    policy: ParsePolicy = MP_PRODUCTION,
    *,
    batch_id: str | None = None,
    tags: Sequence[str] = (),
) -> ParsedCalculation:
    """Parse a calculation.

    The task document and the trajectory are made now. The large objects are
    made when `ParsedCalculation.objects()` is iterated through, so that they
    do not have to be in memory together.

    A calculation which cannot be read at all does not raise an exception: the
    result has no task, and an outcome of `error`.

    Parameters
    -----------
    source : CalculationSource
        The calculation.
    identifier : str
        The identifier of the calculation. It is the task_id of the task, and
        the identifier of every row made from the calculation. It can be given in any
        of the forms of `IdentifierType`.
    policy : ParsePolicy
        Which large objects to parse, `MP_PRODUCTION` by default.
    batch_id : str or None
        The batch identifier of the task.
    tags : sequence of str
        Metadata tags of the task, in addition to any in the transformations file.

    Returns
    -----------
    ParsedCalculation
    """
    identifier = _IDENTIFIER_ADAPTER.validate_python(identifier)

    completed_at: datetime | None = None
    try:
        completed_at = source.completed_at
        return _parse_calculation(
            source, identifier, policy, completed_at, batch_id, tags
        )
    except Exception as exc:
        parsed = ParsedCalculation(
            identifier=identifier,
            outcome=ParseOutcome.ERROR,  # type: ignore[arg-type]
            dir_name=_safe(lambda: source.dir_name, ""),
            calc_suffix=_safe(lambda: source.calc_suffix, STANDARD_CALC_SUFFIX),
            completed_at=completed_at,
            exception=exc,
        )
        parsed._record_error("the calculation", exc)
        return parsed


def _safe(get: Any, default: Any) -> Any:
    try:
        return get()
    except Exception:
        return default


def _parse_calculation(
    source: CalculationSource,
    identifier: str,
    policy: ParsePolicy,
    completed_at: datetime,
    batch_id: str | None,
    tags: Sequence[str],
) -> ParsedCalculation:
    files = source.files
    missing = [
        name
        for name, path in (
            ("vasprun.xml", files.vasprun),
            ("OUTCAR", files.outcar),
            ("CONTCAR", files.contcar),
        )
        if path is None
    ]
    if missing:
        raise FileNotFoundError(f"The calculation has no {', '.join(missing)}.")

    kwargs: dict[str, Any] = files.to_calculation_kwargs(resolve=False)
    if not policy.average_locpot:
        kwargs.pop("volumetric_files", None)
    calc_doc, _, vasprun = Calculation._from_vasp_files(
        files.directory,
        source.calc_suffix,
        **kwargs,
        average_locpot=policy.average_locpot,
        store_trajectory=StoreTrajectoryOption.NO,
    )

    transformations, icsd_id, transformation_tags, _ = _parse_transformations_file(
        files.workflow.get("transformations.json")
    )
    task = CoreTaskDoc.from_calculation(
        calc_doc,
        dir_name=source.dir_name,
        calc_suffix=source.calc_suffix,
        completed_at=completed_at,
        orig_inputs=_parse_orig_input_files(files.orig_inputs),
        transformations=transformations,
        icsd_id=icsd_id,
        task_id=identifier,
        batch_id=batch_id,
        tags=[*tags, *transformation_tags],
    )
    trajectory = get_trajectories_from_calculations([calc_doc], identifier=identifier)[
        0
    ]

    assert task.run_type is not None and task.task_type is not None
    header = ParsedRowHeader(
        identifier=identifier,
        completed_at=completed_at,
        run_type=task.run_type,
        task_type=task.task_type,  # type: ignore[arg-type]
        formula_pretty=task.formula_pretty,  # type: ignore[arg-type]
        chemsys=task.chemsys,  # type: ignore[arg-type]
    )

    parsed = ParsedCalculation(
        identifier=identifier,
        outcome=policy.outcome(calc_doc),
        dir_name=source.dir_name,
        calc_suffix=source.calc_suffix,
        completed_at=completed_at,
        task=task,
        trajectory=trajectory,
        header=header,
        _policy=policy,
        _files=files,
    )
    if parsed.outcome == ParseOutcome.PARSED:
        # keep only what the large objects need. The band structure is read from
        # the file again, so it does not need the Vasprun, which can be freed first
        if policy.wants_dos(header.task_type):
            parsed._vasprun = vasprun
        if policy.wants_bandstructure(header.task_type):
            parsed._bandstructure_input = _BandStructureInput(
                vasprun_file=files.vasprun,  # type: ignore[arg-type]
                incar=dict(vasprun.incar),
                kpoints_file=files.inputs.get("KPOINTS"),
                task_type=header.task_type,
            )
    return parsed
