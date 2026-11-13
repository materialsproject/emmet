"""Read the calculation in a raw VASP archive as a source for parsing."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from emmet.archival.base import Archiver
from emmet.archival.vasp.metadata import ArchiveMetadata
from emmet.archival.vasp.raw import RawArchive
from emmet.core.vasp.parse import DEFAULT_POLICY, ParsePolicy, parse_calculation
from emmet.core.vasp.utils import discover_calculations

if TYPE_CHECKING:
    from collections.abc import Iterator, MutableMapping, Sequence
    from typing import Self

    from emmet.core.tasks import CoreTaskDoc
    from emmet.core.types.typing import FSPathType
    from emmet.core.vasp.parse import ParsedCalculation
    from emmet.core.vasp.utils import CalculationFiles

VASPRUN_KEY = "output/vasprun.xml"


class ArchiveSource:
    """The calculation in a raw VASP archive, as a `CalculationSource`.

    The files of the archive are extracted when it is entered, and deleted
    when it is left, so a `ParsedCalculation` has to be used inside the `with`
    block. They are named as in the archive: without suffixes or
    compression extensions.

    ```
    with ArchiveSource("archive.h5") as source:
        parsed = parse_calculation(source, identifier)
        for table, row in parsed.objects():
            ...
    ```

    Parameters
    -----------
    archive_path : FSPathType
        The archive.
    group_key : str or None
        If not None, the group of the archive which holds the calculation.
    zarr_store : MutableMapping or None
        If specified, the ZARR store to begin file root at.
    """

    def __init__(
        self,
        archive_path: FSPathType,
        group_key: str | None = None,
        zarr_store: MutableMapping | None = None,
    ) -> None:
        self.archive_path = archive_path
        self.group_key = group_key
        self.zarr_store = zarr_store
        self._tmp_dir: TemporaryDirectory | None = None
        self._files: CalculationFiles | None = None
        self._metadata: ArchiveMetadata | None = None
        self._vasprun_mtime: datetime | None = None

    def __enter__(self) -> Self:
        self._tmp_dir = TemporaryDirectory()
        try:
            self._extract(Path(self._tmp_dir.name))
        except BaseException:
            self._tmp_dir.cleanup()
            self._tmp_dir = None
            raise
        return self

    def __exit__(self, *exc_info) -> None:
        if self._tmp_dir is not None:
            self._tmp_dir.cleanup()
        self._tmp_dir = None
        self._files = None

    def _extract(self, output_dir: Path) -> None:
        with Archiver._open_hdf5_like(
            self.archive_path,
            mode="r",
            group_key=self.group_key,
            zarr_store=self.zarr_store,
        ) as group:
            self._metadata = ArchiveMetadata.from_attrs(group.attrs)
            if VASPRUN_KEY in group:
                self._vasprun_mtime = datetime.fromisoformat(
                    str(group[VASPRUN_KEY].attrs["mtime"])
                )
            RawArchive._extract_from_hdf5_like(group, output_dir=output_dir)

        # the files have no suffixes, so there is one calculation
        calculations = discover_calculations(output_dir, require_vasprun=False)
        if len(calculations) != 1:
            raise ValueError(
                f"Expected the archive {self.archive_path} to have the files of one "
                f"VASP calculation, found {len(calculations)}."
            )
        (self._files,) = calculations.values()

    @property
    def metadata(self) -> ArchiveMetadata:
        """The metadata of the archive."""
        if self._metadata is None:
            raise RuntimeError("The archive has to be opened with a `with` block.")
        return self._metadata

    @property
    def files(self) -> CalculationFiles:
        if self._files is None:
            raise RuntimeError("The archive has to be opened with a `with` block.")
        return self._files

    @property
    def dir_name(self) -> str:
        return self.metadata.source_dir_name

    @property
    def calc_suffix(self) -> str:
        return self.metadata.calc_suffix

    @property
    def completed_at(self) -> datetime:
        """When the calculation completed.

        This is `completed_at_override` if the archive has it. Otherwise it is
        the modification time which the vasprun.xml had when it was archived.
        Raises a FileNotFoundError if the archive has neither, which is the case
        for the archive of a calculation which has no vasprun.xml.
        """
        if (completed_at := self.metadata.completed_at_override) is not None:
            return completed_at.astimezone(UTC)
        if self._vasprun_mtime is None:
            raise FileNotFoundError(
                f"{self.archive_path} has no vasprun.xml, so there is no time at "
                "which the calculation completed, and no completed_at_override."
            )
        return self._vasprun_mtime.astimezone(UTC)


@contextmanager
def parse_archive(
    archive_path: FSPathType,
    identifier: str,
    policy: ParsePolicy = DEFAULT_POLICY,
    *,
    group_key: str | None = None,
    zarr_store: MutableMapping | None = None,
    batch_id: str | None = None,
    tags: Sequence[str] = (),
) -> Iterator[ParsedCalculation]:
    """Parse the calculation in an archive, see `emmet.core.vasp.parse.parse_calculation`.

    The result has to be used inside the `with` block, as it reads the
    files of the calculation when its `objects()` are iterated through.
    """
    with ArchiveSource(archive_path, group_key, zarr_store) as source:
        yield parse_calculation(
            source, identifier, policy, batch_id=batch_id, tags=tags
        )


def archive_to_core_task_doc(
    archive_path: FSPathType,
    identifier: str,
    *,
    group_key: str | None = None,
    zarr_store: MutableMapping | None = None,
    **kwargs,
) -> CoreTaskDoc:
    """Make the CoreTaskDoc of the calculation in an archive.

    Raises the exception, if the calculation could not be read.
    """
    with parse_archive(
        archive_path, identifier, group_key=group_key, zarr_store=zarr_store, **kwargs
    ) as parsed:
        if parsed.task is None:
            raise parsed.exception or ValueError("The calculation could not be read.")
        return parsed.task
