"""Define the row models of the parsed-tier tables of large VASP objects.

Each model here describes one row of a table: an emmet-core model of a
VASP object (e.g., `ElectronicDos`), plus a header of top-level columns used
to partition, sort, and filter the table without joining on other tables.

The schema of every table is `pa.schema(arrowize(<row model>))`: no schemas
are defined separately from the models. Arrow-specific column types, such as
float32 columns, are declared on the fields of the models themselves.

Importing this module does not require pyarrow. Table construction and I/O
is the responsibility of whatever writes the tables.

Projections are stored apart from the DOS and band structure they belong to,
because they are far larger than the rest of the data and are rarely needed
together with it. A DOS or band structure therefore has two tables, which
are joined on `identifier`: one with the rows of `DosRow` / `BandStructureRow`
(no projections), and one with the rows of `DosProjectionsRow` /
`BandStructureProjectionsRow`. Use `dos_from_rows` / `band_structure_from_rows`
to put them back together.

Because the models validate their input, rows should be constructed directly
from pymatgen objects, which avoids copying very large arrays:

    >>> VolumetricRow.from_pmg(
    ...     chgcar,
    ...     identifier="mp-1",
    ...     file_name="CHGCAR.relax1.gz",
    ...     completed_at=completed_at,
    ...     run_type=RunType.GGA,
    ...     task_type=TaskType.Static,
    ...     formula_pretty="Si",
    ...     chemsys="Si",
    ... )

and not by dumping an existing model and validating that dump again.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from emmet.core.band_theory import (
    BSPathType,
    ElectronicBS,
    ElectronicDos,
    ProjectedBS,
    ProjectedDos,
)
from emmet.core.tasks import CoreTaskDoc
from emmet.core.trajectory import RelaxTrajectory
from emmet.core.types.enums import ValueEnum
from emmet.core.types.typing import TaskIdentifierType
from emmet.core.utils import convert_datetime, utcnow
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.vasp.models import VOLUMETRIC_PARSERS, ChgcarLike, volumetric_file_type

if TYPE_CHECKING:
    from typing import Any, Self


def _require_datetime(v: Any) -> datetime:
    """Convert to a timezone-aware datetime, but do not silently default to now."""
    if not v:
        raise ValueError(
            "A completion time is required, it determines the partition of the row."
        )
    return convert_datetime(v)


def _optional_datetime(v: Any) -> datetime | None:
    """Convert to a timezone-aware datetime, or None if there is no value."""
    return convert_datetime(v) if v else None


class ParsedRowHeader(BaseModel):
    """Top-level columns shared by the rows of every table of large VASP objects.

    These are stored on each row, rather than found by joining on the tasks
    table, so that tables can be partitioned, sorted, and filtered on their own.
    The calculation directory and suffix are not repeated here: they are
    stored once in the tasks table, which can be joined on `identifier`.
    """

    identifier: TaskIdentifierType = Field(
        description="The identifier of the calculation. Joins to the task_id "
        "of the tasks table."
    )
    completed_at: Annotated[datetime, BeforeValidator(_require_datetime)] = Field(
        description="When the calculation was completed. Determines the date "
        "partition of the row."
    )
    year: int | None = Field(
        None, description="The year of `completed_at`. Always derived from it."
    )
    month: int | None = Field(
        None, description="The month of `completed_at`. Always derived from it."
    )
    day: int | None = Field(
        None, description="The day of `completed_at`. Always derived from it."
    )
    run_type: RunType = Field(description="The functional used in the calculation.")
    task_type: TaskType = Field(description="The type of calculation.")
    formula_pretty: str = Field(description="The reduced formula of the structure.")
    chemsys: str = Field(
        description="The chemical system of the structure, e.g., Li-Fe-O."
    )

    @model_validator(mode="after")
    def set_partition_date(self) -> Self:
        """Derive the date columns from `completed_at`, so they cannot disagree."""
        self.year = self.completed_at.year
        self.month = self.completed_at.month
        self.day = self.completed_at.day
        return self


class DosRow(ParsedRowHeader, ElectronicDos):
    """A row of the total density of states table.

    The projections are not a column of the table. They are kept on the
    row for the convenience of building the row of the projections table from it.
    """

    projected_densities: ProjectedDos | None = Field(
        None,
        exclude=True,
        description="The orbital- and site-projected DOS. Not stored in this "
        "table, see DosProjectionsRow.",
    )


class DosProjectionsRow(ParsedRowHeader, ProjectedDos):
    """A row of the projected density of states table."""


class BandStructureRow(ParsedRowHeader, ElectronicBS):
    """A row of the band structure table.

    The projections are not a column of the table. They are kept on the
    row for the convenience of building the row of the projections table from it.
    """

    projections: ProjectedBS | None = Field(
        None,
        exclude=True,
        description="The site- and spin-orbital-projected band structure. Not "
        "stored in this table, see BandStructureProjectionsRow.",
    )


class BandStructureProjectionsRow(ParsedRowHeader, ProjectedBS):
    """A row of the projected band structure table."""

    path_convention: BSPathType = Field(
        description="High symmetry path convention of the band structure. "
        "A copy of the column of the band structure table, which partitions both tables."
    )


class VolumetricRow(ParsedRowHeader, ChgcarLike):
    """A row of a volumetric data table: one row per volumetric file.

    All volumetric tables have the same schema, regardless of the type of
    the file (CHGCAR, LOCPOT, ...), which is given by the name of the table.
    The `data_aug` column is empty for files which have no augmentation
    charges, like LOCPOT and ELFCAR.
    """

    file_name: str = Field(
        description="The name of the volumetric file, including any calculation "
        "suffix and compression extension, e.g., CHGCAR.relax1.gz"
    )


def _assemble_row(
    row_cls: type[BaseModel], header: ParsedRowHeader, part: BaseModel, **extra: Any
) -> Any:
    """Make a row from an already validated header and part of another model.

    The values are not validated again, so their (potentially very large)
    arrays are shared with `part`, not copied.
    """
    values = {name: getattr(header, name) for name in ParsedRowHeader.model_fields}
    values.update({name: getattr(part, name) for name in type(part).model_fields})
    values.update(extra)
    return row_cls.model_construct(**values)


def split_dos_row(row: DosRow) -> tuple[DosRow, DosProjectionsRow | None]:
    """Split the projections of a DOS into their own row.

    The projections are removed from the DOS row so they are not held twice.

    Returns
    -----------
    DosRow
        The row (the same object as the input) with no projections.
    DosProjectionsRow or None
        None if the DOS has no projections.
    """
    projections = row.projected_densities
    row.projected_densities = None
    if projections is None:
        return row, None
    return row, _assemble_row(DosProjectionsRow, row, projections)


def split_band_structure_row(
    row: BandStructureRow,
) -> tuple[BandStructureRow, BandStructureProjectionsRow | None]:
    """Split the projections of a band structure into their own row.

    The projections are removed from the band structure row so they are
    not held twice.

    Returns
    -----------
    BandStructureRow
        The row (the same object as the input) with no projections.
    BandStructureProjectionsRow or None
        None if the band structure has no projections.
    """
    projections = row.projections
    row.projections = None
    if projections is None:
        return row, None
    return row, _assemble_row(
        BandStructureProjectionsRow,
        row,
        projections,
        path_convention=row.path_convention,
    )


def dos_from_rows(
    dos: DosRow | ElectronicDos, projections: DosProjectionsRow | None = None
) -> ElectronicDos:
    """Rebuild a DOS from its row and, optionally, the row of its projections.

    Parameters
    -----------
    dos : DosRow
        The row of the total DOS table.
    projections : DosProjectionsRow or None
        The row of the projected DOS table with the same identifier, if the
        projections are wanted.

    Returns
    -----------
    ElectronicDos
        Which can be converted to a pymatgen object with `.to_pmg()`.
    """
    if projections is not None and projections.identifier != getattr(
        dos, "identifier", None
    ):
        raise ValueError(
            f"The projections of {projections.identifier} do not belong to the "
            f"DOS of {getattr(dos, 'identifier', None)}."
        )
    config = {name: getattr(dos, name) for name in ElectronicDos.model_fields}
    if projections is not None:
        config["projected_densities"] = ProjectedDos(
            **{name: getattr(projections, name) for name in ProjectedDos.model_fields}
        )
    return ElectronicDos(**config)


def band_structure_from_rows(
    band_structure: BandStructureRow | ElectronicBS,
    projections: BandStructureProjectionsRow | None = None,
) -> ElectronicBS:
    """Rebuild a band structure from its row and, optionally, its projections row.

    Parameters
    -----------
    band_structure : BandStructureRow
        The row of the band structure table.
    projections : BandStructureProjectionsRow or None
        The row of the projected band structure table with the same
        identifier, if the projections are wanted.

    Returns
    -----------
    ElectronicBS
        Which can be converted to a pymatgen object with `.to_pmg()`.
    """
    if projections is not None and projections.identifier != getattr(
        band_structure, "identifier", None
    ):
        raise ValueError(
            f"The projections of {projections.identifier} do not belong to the "
            f"band structure of {getattr(band_structure, 'identifier', None)}."
        )
    config = {name: getattr(band_structure, name) for name in ElectronicBS.model_fields}
    if projections is not None:
        config["projections"] = ProjectedBS(
            **{name: getattr(projections, name) for name in ProjectedBS.model_fields}
        )
    return ElectronicBS(**config)


class ValidationRow(ParsedRowHeader):
    """A row of the validation table, which has the results of validating a task."""

    valid: bool = Field(description="Whether the calculation passed validation.")
    reasons: list[str] = Field(
        [], description="The reasons the calculation failed validation, if any."
    )
    warnings: list[str] = Field(
        [], description="Warnings raised during validation, if any."
    )


# The convergence data is computed by RelaxTrajectory, as properties, and is stored as
# columns of the trajectory table by the row. That the row's fields have the names of
# those properties is intended, and pydantic warns about it. Only that is silenced.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r'Field name "has_full_output" in "TrajectoryRow" shadows an attribute',
        category=UserWarning,
    )

    class TrajectoryRow(RelaxTrajectory):
        """A row of the trajectory table: a trajectory with its convergence data.

        The convergence data of a trajectory is computed from it, and computed
        properties are not columns of a table, so they are stored here. They are
        columns of the trajectories already in production, which are partitioned
        by run type.
        """

        has_full_output: bool = Field(
            description="Whether the trajectory has all structures and SCF convergence data."
        )
        energy_convergence: list[float] | None = Field(
            None, description="Convergence of the energy, see `convergence_data`."
        )
        e_fr_energy_convergence: list[float] | None = Field(
            None, description="Convergence of the free energy, see `convergence_data`."
        )
        e_wo_entrp_convergence: list[float] | None = Field(
            None,
            description="Convergence of the energy without entropy, see `convergence_data`.",
        )
        forces_convergence: list[float] | None = Field(
            None, description="Convergence of the forces, see `convergence_data`."
        )

        @classmethod
        def from_trajectory(cls, trajectory: RelaxTrajectory) -> TrajectoryRow:
            """Make a row from a trajectory, computing its convergence data."""
            values = {
                name: getattr(trajectory, name) for name in RelaxTrajectory.model_fields
            }
            convergence = trajectory.convergence_data
            return cls(
                **values,
                has_full_output=trajectory.has_full_output,
                **{
                    f"{name}_convergence": convergence.get(name)
                    for name in ("energy", "e_fr_energy", "e_wo_entrp", "forces")
                },
            )


class ParseOutcome(ValueEnum):
    """What came of parsing a calculation."""

    PARSED = "parsed"
    SKIPPED_FAILED = "skipped_failed"
    SKIPPED_UNRECOGNIZED = "skipped_unrecognized"
    ERROR = "error"


class ManifestRow(BaseModel):
    """A row of the manifest table, which records the parsing of every calculation.

    A calculation gets a row whatever came of parsing it, even if it
    could not be read at all, so that nothing disappears silently. It can also
    be used to find out which calculations have been parsed already, by
    their `dir_name` and `calc_suffix`.

    The manifest does not have the header of the other tables, because the
    properties of a calculation which could not be read are not known.
    """

    identifier: TaskIdentifierType = Field(
        description="The identifier assigned to the calculation."
    )
    dir_name: str = Field(
        description="The directory the calculation was parsed from. Together with "
        "the calc_suffix it identifies the calculation."
    )
    calc_suffix: str = Field(
        description="The suffix of the calculation in the directory, or standard."
    )
    completed_at: Annotated[datetime | None, BeforeValidator(_optional_datetime)] = (
        Field(None, description="When the calculation was completed, if known.")
    )
    parsed_at: datetime = Field(
        default_factory=utcnow, description="When the calculation was parsed."
    )
    outcome: ParseOutcome = Field(description="What came of parsing the calculation.")
    run_type: RunType | None = Field(
        None, description="The functional used in the calculation, if known."
    )
    task_type: TaskType | None = Field(
        None, description="The type of calculation, if known."
    )
    tables: list[str] = Field(
        [], description="The tables which received a row for this calculation."
    )
    errors: list[str] = Field(
        [], description="The problems which occurred while parsing the calculation."
    )


@dataclass(frozen=True)
class TableSpec:
    """The row model and physical layout of a table.

    Attributes
    -----------
    name : str
        The name of the table.
    row_model : type[BaseModel]
        The model of a row. The table schema is `pa.schema(arrowize(row_model))`.
    partition_by : tuple of str
        The columns the table is partitioned on, in order, e.g.,
        (year, month, day, run_type) gives a layout like `2026/10/28/GGA/`.
        Empty if the table is not partitioned.
    zorder_by : tuple of str
        The columns the table is sorted / Z-ordered on, within partitions.
    """

    name: str
    row_model: type[BaseModel]
    partition_by: tuple[str, ...] = ()
    zorder_by: tuple[str, ...] = ("identifier",)
    column_order: tuple[str, ...] | None = None

    @property
    def columns(self) -> set[str]:
        """The top-level columns of the table."""
        return {
            name
            for name, field in self.row_model.model_fields.items()
            if not field.exclude
        }

    @property
    def ordered_columns(self) -> list[str]:
        """The columns of the table, in the order they are stored in.

        This is `column_order` if there is one, and otherwise the order
        of the fields of the row model.
        """
        if self.column_order is not None:
            return list(self.column_order)
        return [
            name
            for name, field in self.row_model.model_fields.items()
            if not field.exclude
        ]


_VOLUMETRIC_PARTITION = ("year", "month", "day", "run_type")

# the order of the columns of the trajectories in production: the columns they are
# found by first, then the rest alphabetically
_TRAJECTORY_PRIORITY = ("has_full_output", "identifier", "run_type", "task_type")
_TRAJECTORY_COLUMNS = (
    *_TRAJECTORY_PRIORITY,
    *sorted(
        name
        for name, field in TrajectoryRow.model_fields.items()
        if name not in _TRAJECTORY_PRIORITY and not field.exclude
    ),
)

PARSED_TABLES: dict[str, TableSpec] = {
    "total-dos": TableSpec("total-dos", DosRow, partition_by=("run_type",)),
    "projected-dos": TableSpec(
        "projected-dos", DosProjectionsRow, partition_by=("run_type",)
    ),
    "bandstructures": TableSpec(
        "bandstructures", BandStructureRow, partition_by=("run_type", "path_convention")
    ),
    "projected-bandstructures": TableSpec(
        "projected-bandstructures",
        BandStructureProjectionsRow,
        partition_by=("run_type", "path_convention"),
    ),
    "validation": TableSpec("validation", ValidationRow),
    "manifest": TableSpec("manifest", ManifestRow),
    "tasks": TableSpec("tasks", CoreTaskDoc, zorder_by=("task_id",)),
    "trajectories": TableSpec(
        "trajectories",
        TrajectoryRow,
        partition_by=("run_type",),
        column_order=_TRAJECTORY_COLUMNS,
    ),
    **{
        file_type.lower(): TableSpec(
            file_type.lower(), VolumetricRow, partition_by=_VOLUMETRIC_PARTITION
        )
        for file_type in VOLUMETRIC_PARSERS
    },
}
"""The tables of the parsed tier of large objects, by name.

The names of the DOS and band structure tables, and the order of their
partitions, are those of the tables already in production.

There is one table for each type of volumetric file, named after the file
in lowercase (`chgcar`, `aeccar0`, `locpot`, ...). These all use `VolumetricRow`.

The tasks table is not partitioned, and the trajectories table is partitioned
by run_type.
"""


def volumetric_table_name(file_name: str) -> str | None:
    """Get the name of the table a volumetric file belongs in.

    Parameters
    -----------
    file_name : str
        The name of a file, e.g., "CHGCAR.relax1.gz".

    Returns
    -----------
    str or None
        The name of the table in `PARSED_TABLES`, or None if the file is
        not a volumetric file.
    """
    file_type = volumetric_file_type(file_name)
    return file_type.lower() if file_type else None
