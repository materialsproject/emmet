"""Define the row models of the parsed-tier tables of large VASP objects.

Each model here describes one row of a table: an emmet-core model of a
VASP object (e.g., `ElectronicDos`), plus a header of top-level columns used
to partition, sort, and filter the table without joining on other tables.

The schema of every table is `pa.schema(arrowize(<row model>))`: no schemas
are defined separately from the models. Arrow-specific column types, such as
float32 columns, are declared on the fields of the models themselves.

Importing this module does not require pyarrow. Table construction and I/O
is the responsibility of whatever writes the tables.

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

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from emmet.core.band_theory import ElectronicBS, ElectronicDos
from emmet.core.utils import convert_datetime
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.vasp.models import VOLUMETRIC_PARSERS, ChgcarLike, volumetric_file_type
from emmet.core.types.typing import IdentifierType

if TYPE_CHECKING:
    from typing import Any, Self


def _require_datetime(v: Any) -> datetime:
    """Convert to a timezone-aware datetime, but do not silently default to now."""
    if not v:
        raise ValueError(
            "A completion time is required, it determines the partition of the row."
        )
    return convert_datetime(v)


class ParsedRowHeader(BaseModel):
    """Top-level columns shared by the rows of every table of large VASP objects.

    These are stored on each row, rather than found by joining on the tasks
    table, so that tables can be partitioned, sorted, and filtered on their own.
    The calculation directory and suffix are not repeated here: they are
    stored once in the tasks table, which can be joined on `identifier`.
    """

    identifier: IdentifierType = Field(
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
    """A row of the density of states table."""


class BandStructureRow(ParsedRowHeader, ElectronicBS):
    """A row of the band structure table."""


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


class ValidationRow(ParsedRowHeader):
    """A row of the validation table, which has the results of validating a task."""

    valid: bool = Field(description="Whether the calculation passed validation.")
    reasons: list[str] = Field(
        [], description="The reasons the calculation failed validation, if any."
    )
    warnings: list[str] = Field(
        [], description="Warnings raised during validation, if any."
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

    @property
    def columns(self) -> set[str]:
        """The top-level columns of the table."""
        return set(self.row_model.model_fields)


_VOLUMETRIC_PARTITION = ("year", "month", "day", "run_type")

PARSED_TABLES: dict[str, TableSpec] = {
    "dos": TableSpec("dos", DosRow, partition_by=("run_type",)),
    "bandstructure": TableSpec(
        "bandstructure", BandStructureRow, partition_by=("run_type", "path_convention")
    ),
    "validation": TableSpec("validation", ValidationRow),
    **{
        file_type.lower(): TableSpec(
            file_type.lower(), VolumetricRow, partition_by=_VOLUMETRIC_PARTITION
        )
        for file_type in VOLUMETRIC_PARSERS
    },
}
"""The tables of the parsed tier of large objects, by name.

There is one table for each type of volumetric file, named after the file
in lowercase (`chgcar`, `aeccar0`, `locpot`, ...). These all use `VolumetricRow`.

The tasks table (not partitioned) and the trajectory table (partitioned by
run_type) are not listed here.
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
