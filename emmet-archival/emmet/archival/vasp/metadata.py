"""Define the metadata which every raw VASP archive carries."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from emmet.core.vasp.utils import STANDARD_CALC_SUFFIX

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any, Self

ARCHIVE_VERSION = 1
"""The version of the layout of raw archives, and of their metadata."""


class ArchiveMetadata(BaseModel):
    """The attributes of the root of a raw VASP archive.

    These describe what the archive is of and where it came from, as
    opposed to the attributes of its files (original name, modification time,
    and hashes), which describe each of them. Every archive is of one calculation.
    """

    model_config = ConfigDict(extra="forbid")

    calculation_id: UUID = Field(
        description="The identifier of the calculation, which names the archive."
    )
    source_dir_name: str = Field(
        description="Where the calculation came from, which becomes the dir_name of "
        "what is parsed from the archive. Whoever makes the archive chooses it. "
        "For example, the `host:/path` of the directory the files were in (see "
        "`emmet.core.utils.get_uri`), or an identifier which does not reveal a "
        "local path, like `submission://{submission_id}/{calculation_id}`."
    )
    calc_suffix: str = Field(
        STANDARD_CALC_SUFFIX,
        description="The suffix of the calculation in its directory, e.g., relax1, "
        "or standard if its files have none.",
    )
    submission_id: UUID | None = Field(
        None, description="The submission the archive was made for, if any."
    )
    snapshot_id: str | None = Field(
        None, description="The snapshot of the submission the archive was made for."
    )
    completed_at_override: datetime | None = Field(
        None,
        description="When the calculation completed, if it is already known from "
        "elsewhere, e.g., for calculations which were parsed before they were "
        "archived, so that the archive agrees with what was recorded. If set, it is "
        "used instead of the modification time of the vasprun.xml.",
    )
    archive_version: int = Field(
        ARCHIVE_VERSION, description="The version of the archive layout."
    )

    @field_validator("completed_at_override")
    @classmethod
    def _require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("completed_at_override must have a timezone.")
        return value

    def to_attrs(self) -> dict[str, str | int]:
        """The metadata as attributes of an archive, which are JSON-like.

        Metadata which is not set is left out.
        """
        return self.model_dump(mode="json", exclude_none=True)

    @classmethod
    def from_attrs(cls, attrs: Mapping[str, Any]) -> Self:
        """Read the metadata from the attributes of an archive."""
        return cls.model_validate(dict(attrs))
