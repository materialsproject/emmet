from pathlib import Path
from emmet.cli.submission import CalculationMetadata, CalculationLocator, Submission
from emmet.cli.utils import EmmetCliError
from emmet.core.vasp.utils import FileMetadata
import pytest


class RecordingUploader:
    def __init__(self, error=None):
        self.error = error
        self.uploads = []

    def upload(self, submission_id, changes):
        if self.error:
            raise self.error
        self.uploads.append((submission_id, changes))


@pytest.fixture(scope="session")
def tmp_structure(tmp_path_factory):
    directory_structure = {
        "other_calc/00/": ["INCAR.gz", "KPOINTS", "POSCAR.gz", "garbage"],
        "other_calc/01/": [
            "INCAR.gz",
            "CHGCAR",
            "CONTCAR.gz",
            "KPOINTS",
            "OUTCAR",
            "POSCAR.gz",
            "POTCAR.bz2",
            "vasprun.xml",
        ],
    }
    tmp_dir = tmp_path_factory.mktemp("other_test_dir")

    tmp_structure = {}
    for calc_dir, files in directory_structure.items():
        p = tmp_dir / calc_dir
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        a_file = None
        for f in files:
            (p / f).touch()
            a_file = p / f
        if calc_dir == "other_calc/00/":
            tmp_structure[calc_dir] = p
        else:
            tmp_structure[calc_dir] = a_file
    return tmp_structure


@pytest.fixture()
def calculation_metadata(tmp_path):
    files = []
    for index in range(3):
        file_path = tmp_path / f"file-{index}"
        file_path.write_text(f"initial content {index}")
        file_metadata = FileMetadata(name=file_path.name, path=file_path)
        file_metadata.compute_hash()
        files.append(file_metadata)

    return CalculationMetadata(
        files=files,
        calc_valid=True,
        calc_validation_errors=[],
    )


def verify_submission_calculations_against_tmp_dir_data(calculations):
    for locator, cm in calculations:
        path = locator.path
        if path.name == "00":
            assert locator.modifier == "standard"
            assert len(cm.files) == 3
        elif path.name == "01":
            assert locator.modifier == "standard"
            assert len(cm.files) == 8
        elif path.name == "02":
            assert locator.modifier == "standard"
            assert len(cm.files) == 3
        elif path.name == "neb_calc":
            assert locator.modifier == "standard"
            assert len(cm.files) == 4
        elif path.name == "launcher_2025_02_31_0001":
            if locator.modifier == "relax1":
                assert len(cm.files) == 9
            elif locator.modifier == "relax2":
                assert len(cm.files) == 6
            else:
                assert locator.modifier == "standard"
                assert len(cm.files) == 4
        else:
            assert path is None


def test_from_paths(tmp_dir):
    submission = Submission.from_paths(paths=[tmp_dir])

    assert len(submission.calculations) == 7
    verify_submission_calculations_against_tmp_dir_data(submission.calculations)


def test_save_and_load(sub_file):
    # conftest already creates a saved file so re-using that
    sub = Submission.load(Path(sub_file))
    verify_submission_calculations_against_tmp_dir_data(sub.calculations)


def test_add_to(sub_file, tmp_structure):
    sub = Submission.load(Path(sub_file))

    # test adding already present paths and files
    to_add_path = []
    for locator, cm in sub.calculations:
        if "neb_calc/01" in str(locator.path):
            to_add_path.append(locator.path)
        elif (
            "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001"
            in str(locator.path)
            and locator.modifier == "relax1"
        ):
            to_add_path.append(cm.files[0].path)

    assert len(to_add_path) == 2

    added = sub.add_to(to_add_path)
    assert len(added) == 0

    # test adding new paths and files too
    to_add_path = to_add_path + list(tmp_structure.values())
    assert len(to_add_path) == 4
    added = sub.add_to(to_add_path)
    assert len(added) == 4
    assert len(sub.calculations) == 9


def test_remove_from(sub_file, tmp_structure):
    sub = Submission.load(Path(sub_file))

    # test removing paths and files not present
    removed = sub.remove_from(tmp_structure.values())
    assert len(removed) == 0

    # test removing present paths and files too
    to_remove_path = []
    for locator, cm in sub.calculations:
        if "neb_calc/01" in str(locator.path):
            to_remove_path.append(locator.path)
        elif (
            "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001"
            in str(locator.path)
            and locator.modifier == "relax1"
        ):
            to_remove_path.append(cm.files[0].path)

    assert len(to_remove_path) == 2

    removed = sub.remove_from(to_remove_path + list(tmp_structure.values()))
    assert len(removed) == 9


@pytest.mark.parametrize("changed_index", [0, 1, 2])
def test_refresh_invalidates_cached_validation(calculation_metadata, changed_index):
    original_hashes = [file.hash for file in calculation_metadata.files]
    changed_file = calculation_metadata.files[changed_index]
    changed_file.path.write_text("changed content")

    calculation_metadata.refresh()

    assert changed_file.hash != original_hashes[changed_index]
    assert calculation_metadata.calc_valid is None
    assert calculation_metadata.calc_validation_errors == []


def test_refresh_invalidates_cached_validation_for_multiple_changed_files(
    calculation_metadata,
):
    original_hashes = [file.hash for file in calculation_metadata.files]
    changed_indices = {0, 2}
    for index in changed_indices:
        calculation_metadata.files[index].path.write_text(f"changed content {index}")

    calculation_metadata.refresh()

    for index, file in enumerate(calculation_metadata.files):
        if index in changed_indices:
            assert file.hash != original_hashes[index]
        else:
            assert file.hash == original_hashes[index]
    assert calculation_metadata.calc_valid is None
    assert calculation_metadata.calc_validation_errors == []


def test_refresh_preserves_cached_validation_for_unchanged_files(calculation_metadata):
    original_hashes = [file.hash for file in calculation_metadata.files]

    calculation_metadata.refresh()

    assert [file.hash for file in calculation_metadata.files] == original_hashes
    assert calculation_metadata.calc_valid is True
    assert calculation_metadata.calc_validation_errors == []


def test_validate_submission(sub_file, validation_sub_file):
    sub = Submission.load(Path(sub_file))

    assert sub.validate_submission() is False

    sub = Submission.load(Path(validation_sub_file))

    assert sub.validate_submission() is True

    # test parallel validation mode correctness by creating submission more calculations than threshold
    files = next(iter(sub.calculations))[1].files
    calcs = []
    for i in range(Submission.PARALLEL_THRESHOLD + 1):
        calcs.append(
            (
                CalculationLocator(path=Path(f"/{i}"), modifier=None),
                CalculationMetadata(files=files),
            )
        )
    lsub = Submission(calculations=calcs)
    assert lsub.validate_submission() is True


def test_changed_files_to_push(validation_sub_file):
    sub = Submission.load(Path(validation_sub_file))
    uploader = RecordingUploader()

    with pytest.raises(EmmetCliError) as ex_info:
        sub.push(uploader)

    assert "Nothing is staged" in str(ex_info.value)

    changed = sub.stage_for_push()
    assert changed.has_changes
    assert sum(len(change.added_files) for change in changed.changes) == 10
    changed = sub.stage_for_push()
    assert changed.has_changes

    sub.push(uploader)
    assert len(uploader.uploads) == 1
    changed = sub.stage_for_push()
    assert not changed.has_changes


def test_submission_changes_include_file_and_calculation_removals(
    calculation_metadata,
):
    locator = CalculationLocator(path=Path("/calculation"), modifier="standard")
    second = calculation_metadata.model_copy(deep=True)
    second.id = calculation_metadata.id
    submission = Submission(calculations=[(locator, calculation_metadata)])
    submission.calc_history.append([(locator, second)])

    removed_file = calculation_metadata.files.pop()
    changes = submission.get_submission_changes(
        submission.last_pushed(), submission.calculations
    )

    assert changes.has_changes
    assert changes.changes[0].status == "changed"
    assert changes.changes[0].removed_files == [removed_file.name]

    removed_calculation_changes = submission.get_submission_changes(
        submission.calculations, []
    )
    assert removed_calculation_changes.changes[0].status == "removed"
    assert removed_calculation_changes.changes[0].calculation is None


def test_failed_upload_does_not_advance_history(validation_sub_file):
    sub = Submission.load(Path(validation_sub_file))
    sub.stage_for_push()

    with pytest.raises(EmmetCliError, match="remote failure"):
        sub.push(RecordingUploader(EmmetCliError("remote failure")))

    assert sub.calc_history == []
    assert sub.pending_calculations is not None


def test_files_changed_after_staging_block_push(validation_sub_file):
    sub = Submission.load(Path(validation_sub_file))
    uploader = RecordingUploader()
    sub.stage_for_push()
    changed_file = sub.calculations[0][1].files[0].path
    changed_file.write_bytes(changed_file.read_bytes() + b"changed after staging")

    with pytest.raises(EmmetCliError, match="changed since staging"):
        sub.push(uploader)

    assert uploader.uploads == []
    assert sub.calc_history == []
    assert sub.pending_calculations is not None
