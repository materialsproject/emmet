"""An archive and the directory it was made from are parsed to the same data."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import h5py
import pytest

from emmet.archival.vasp.raw import RawArchive
from emmet.archival.vasp.source import (
    ArchiveSource,
    archive_to_core_task_doc,
    parse_archive,
)
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive
from emmet.core.vasp.parse import DirectorySource, parse_calculation

ID = "aaaaaaab"
SOURCE_DIR = "host:/block_1/launcher_1"


@pytest.fixture
def extract():
    """Extract a directory of VASP files, which are removed after the test."""
    extracted = []

    def _extract(fixture: str) -> Path:
        archive = DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz")
        extracted.append(archive)
        return archive.__enter__()

    yield _extract
    for archive in extracted:
        archive.__exit__(None, None, None)


@pytest.fixture
def archive_of(tmp_path, extract):
    """Archive the calculation in a test fixture, returning its directory and archive."""

    def _archive_of(fixture: str, **metadata):
        directory = extract(fixture)
        (raw_archive,) = RawArchive.from_directory(directory)
        path = tmp_path / f"{fixture}.h5"
        raw_archive.to_archive(
            path,
            metadata={
                "calculation_id": str(uuid4()),
                "source_dir_name": SOURCE_DIR,
                **metadata,
            },
        )
        return directory, path

    return _archive_of


def parse_directory(directory):
    (source,) = DirectorySource.from_directory(directory)
    parsed = parse_calculation(source, ID)
    return parsed, list(parsed.objects())


@pytest.mark.parametrize("fixture", ["Si_uniform", "Si_static"])
def test_archive_parses_like_the_directory(archive_of, fixture):
    directory, path = archive_of(fixture)
    expected, expected_rows = parse_directory(directory)
    assert expected.errors == []

    with parse_archive(path, ID) as parsed:
        rows = list(parsed.objects())
        assert parsed.errors == []

        assert parsed.outcome == expected.outcome
        assert parsed.completed_at == expected.completed_at
        assert parsed.calc_suffix == expected.calc_suffix
        assert [t for t, _ in rows] == [t for t, _ in expected_rows]
        assert parsed.manifest_row().tables == expected.manifest_row().tables

    # only where the calculation came from, and the time of parsing, differ
    assert parsed.dir_name == SOURCE_DIR != expected.dir_name
    task, expected_task = parsed.task.model_dump(), expected.task.model_dump()
    assert {k for k in task if task[k] != expected_task[k]} == {
        "dir_name",
        "last_updated",
    }
    assert parsed.trajectory.model_dump() == expected.trajectory.model_dump()

    assert rows
    for (table, row), (_, expected_row) in zip(rows, expected_rows):
        dumped, expected_dumped = row.model_dump(), expected_row.model_dump()
        # the compression extension of files is not kept by archives
        for k in set(dumped):
            if k == "file_name":
                assert dumped[k] == expected_dumped[k].removesuffix(".gz")
            else:
                assert dumped[k] == expected_dumped[k], (table, k)


def test_source_describes_the_archive(archive_of):
    directory, path = archive_of("Si_static")
    with ArchiveSource(path) as source:
        assert source.dir_name == SOURCE_DIR
        assert source.calc_suffix == "standard"
        names = {p.name for p in source.files.file_paths()}
        # files are extracted as they are in the archive: no suffix or compression
        assert {"vasprun.xml", "CHGCAR", "INCAR", "INCAR.orig"} <= names
        files = source.files.file_paths()
        extracted_dir = files[0].parent
        assert extracted_dir.exists()
    # the files do not outlive the source
    assert not extracted_dir.exists()
    with pytest.raises(RuntimeError, match="with"):
        source.files


def test_completed_at_is_the_stored_modification_time(archive_of):
    directory, path = archive_of("Si_static")
    with h5py.File(path, "r+") as f:
        f["output/vasprun.xml"].attrs["mtime"] = "2020-02-03T04:05:06+00:00"
    with ArchiveSource(path) as source:
        assert source.completed_at == datetime(2020, 2, 3, 4, 5, 6, tzinfo=UTC)

    # other zones are given in UTC
    with h5py.File(path, "r+") as f:
        f["output/vasprun.xml"].attrs["mtime"] = "2020-02-03T04:05:06-08:00"
    with ArchiveSource(path) as source:
        assert source.completed_at == datetime(2020, 2, 3, 12, 5, 6, tzinfo=UTC)
        assert source.completed_at.utcoffset() == timedelta(0)


def test_completed_at_override_takes_priority(archive_of):
    completed = datetime(2017, 6, 7, 8, tzinfo=UTC)
    directory, path = archive_of("Si_static", completed_at_override=completed)
    with ArchiveSource(path) as source:
        assert source.completed_at == completed
    with parse_archive(path, ID) as parsed:
        assert parsed.completed_at == completed
        assert parsed.task.completed_at == completed


@pytest.fixture
def unfinished_archive(tmp_path):
    """The archive of a calculation which has no vasprun.xml."""
    calc_dir = tmp_path / "unfinished"
    calc_dir.mkdir()
    (calc_dir / "INCAR").write_text("ENCUT = 520")

    def _unfinished_archive(**metadata):
        (archive,) = RawArchive.from_directory(calc_dir, require_vasprun=False)
        path = calc_dir / "unfinished.h5"
        archive.to_archive(
            path,
            {
                "calculation_id": str(uuid4()),
                "source_dir_name": SOURCE_DIR,
                **metadata,
            },
        )
        return path

    return _unfinished_archive


def test_no_completion_time(unfinished_archive):
    path = unfinished_archive()
    with ArchiveSource(path) as source:
        with pytest.raises(FileNotFoundError, match="no vasprun.xml"):
            source.completed_at
    # the failure is recorded, not raised
    with parse_archive(path, ID) as parsed:
        assert parsed.outcome.value == "error"
        assert parsed.task is None


def test_override_gives_a_completion_time_without_a_vasprun(unfinished_archive):
    completed = datetime(2017, 6, 7, 8, tzinfo=UTC)
    path = unfinished_archive(completed_at_override=completed)
    with ArchiveSource(path) as source:
        assert source.completed_at == completed


def test_to_archive_requires_metadata(tmp_path, extract):
    (raw_archive,) = RawArchive.from_directory(extract("Si_static"))
    with pytest.raises(TypeError, match="metadata"):
        raw_archive.to_archive(tmp_path / "no_metadata.h5")  # type: ignore[call-arg]
    assert not (tmp_path / "no_metadata.h5").exists()


def test_to_core_task_doc(archive_of, unfinished_archive):
    directory, path = archive_of("Si_static", calc_suffix="standard")
    task = archive_to_core_task_doc(path, ID)
    assert str(task.task_id) == ID
    assert task.dir_name == SOURCE_DIR
    assert task.calc_suffix == "standard"

    # a calculation which was archived without its output cannot be read
    with pytest.raises(FileNotFoundError, match="no vasprun.xml"):
        archive_to_core_task_doc(unfinished_archive(), ID)


def test_calculations_of_a_multi_calculation_directory(tmp_path, extract):
    """Each calculation of a directory is archived, and read back, on its own."""
    directory = extract("Si_old_double_relax")
    archives = RawArchive.from_directory(directory)
    sources = DirectorySource.from_directory(directory)
    assert len(archives) == len(sources) == 2
    assert [a.calc_suffix for a in archives] == ["relax1", "relax2"]

    for archive, source in zip(archives, sources):
        path = tmp_path / f"{archive.calc_suffix}.h5"
        archive.to_archive(
            path,
            metadata={"calculation_id": str(uuid4()), "source_dir_name": SOURCE_DIR},
        )
        expected = parse_calculation(source, ID)
        with parse_archive(path, ID) as parsed:
            assert parsed.errors == [] and expected.errors == []
            assert parsed.calc_suffix == expected.calc_suffix == archive.calc_suffix
            assert parsed.task.calc_suffix == archive.calc_suffix
            assert parsed.completed_at == expected.completed_at
            # the original inputs are only the first calculation's, in either
            assert (parsed.task.orig_inputs is None) == (
                expected.task.orig_inputs is None
            )
            task, expected_task = parsed.task.model_dump(), expected.task.model_dump()
            # the archive has the hash of the POTCAR, the vasprun.xml does not
            for spec, expected_spec in zip(
                task["input"]["potcar_spec"], expected_task["input"]["potcar_spec"]
            ):
                assert expected_spec["hash"] is None and spec["hash"]
                spec["hash"] = expected_spec["hash"] = None
            assert {k for k in task if task[k] != expected_task[k]} == {
                "dir_name",
                "last_updated",
            }

    # they were not mixed up: each has its own output
    assert archives[0].file_paths["output/vasprun.xml"].path != (
        archives[1].file_paths["output/vasprun.xml"].path
    )
