from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import h5py
import pytest
from pydantic import ValidationError

from emmet.archival.vasp.metadata import ARCHIVE_VERSION, ArchiveMetadata
from emmet.archival.vasp.raw import RawArchive
from emmet.core.vasp.utils import FileMetadata


def make_archive(directory: Path, calc_suffix: str = "standard") -> RawArchive:
    (directory / "INCAR").write_text("ENCUT = 520")
    return RawArchive.from_files(
        [FileMetadata(name="INCAR", path=directory / "INCAR")],
        root=directory,
        calc_suffix=calc_suffix,
    )


def test_attrs_round_trip():
    calc_id, sub_id = uuid4(), uuid4()
    meta = ArchiveMetadata(
        calculation_id=calc_id,
        source_dir_name=f"submission://{sub_id}/{calc_id}",
        calc_suffix="relax1",
        submission_id=sub_id,
        snapshot_id="abc",
    )
    attrs = meta.to_attrs()
    # only JSON-like values, and nothing which is not set
    assert all(isinstance(v, str | int) for v in attrs.values())
    assert "completed_at_override" not in attrs
    assert attrs["calculation_id"] == str(calc_id)
    assert attrs["archive_version"] == ARCHIVE_VERSION
    assert ArchiveMetadata.from_attrs(attrs) == meta


def test_backfill_metadata():
    completed = datetime(2019, 5, 1, 12, tzinfo=UTC)
    meta = ArchiveMetadata(
        calculation_id=uuid4(),
        source_dir_name="host:/block_2019/launcher_2019",
        completed_at_override=completed,
    )
    assert meta.calc_suffix == "standard" and meta.submission_id is None
    assert (
        ArchiveMetadata.from_attrs(meta.to_attrs()).completed_at_override == completed
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source_dir_name": "host:/a"},  # no calculation id
        {"calculation_id": uuid4()},  # no source
        {"calculation_id": "nope", "source_dir_name": "host:/a"},
        {
            "calculation_id": uuid4(),
            "source_dir_name": "host:/a",
            "completed_at_override": datetime(2019, 5, 1),  # naive
        },
        {"calculation_id": uuid4(), "source_dir_name": "a", "file_path": "/x"},
    ],
)
def test_invalid(kwargs):
    with pytest.raises(ValidationError):
        ArchiveMetadata(**kwargs)


def test_written_to_the_archive(tmp_path, tmp_dir):
    calc_id = uuid4()
    archive = make_archive(tmp_path, calc_suffix="relax1")
    archive.to_archive(
        "archive.h5",
        metadata={
            "calculation_id": str(calc_id),
            "source_dir_name": "host:/some/launcher",
        },
    )
    with h5py.File("archive.h5") as f:
        stored = ArchiveMetadata.from_attrs(f.attrs)
    # the suffix of the archive is used, as the metadata has none
    assert stored.calc_suffix == "relax1"
    assert stored.calculation_id == calc_id


def test_invalid_metadata_writes_nothing(tmp_path, tmp_dir):
    archive = make_archive(tmp_path)
    with pytest.raises(ValidationError):
        archive.to_archive("archive.h5", metadata={"calculation_id": str(uuid4())})
    assert not Path("archive.h5").exists()


def test_suffix_must_match_the_archive(tmp_path, tmp_dir):
    archive = make_archive(tmp_path, calc_suffix="relax1")
    with pytest.raises(ValueError, match="'relax2'.*'relax1'"):
        archive.to_archive(
            "archive.h5",
            metadata=ArchiveMetadata(
                calculation_id=uuid4(), source_dir_name="a", calc_suffix="relax2"
            ),
        )
    assert not Path("archive.h5").exists()
