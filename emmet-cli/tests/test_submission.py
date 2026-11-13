import json
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
            # the files without a suffix (AECCAR0, LOCPOT and the electron-phonon
            # POSCARs) are the last calculation's, not a calculation of their own
            if locator.modifier == "relax1":
                assert len(cm.files) == 9
            else:
                assert locator.modifier == "relax2"
                assert len(cm.files) == 6 + 4
        else:
            assert path is None


def test_from_paths(tmp_dir):
    submission = Submission.from_paths(paths=[tmp_dir])

    assert len(submission.calculations) == 6
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
    assert len(sub.calculations) == 8


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


def make_files(directory: Path, names) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text(f"contents of {name}")
    return directory


def calculation_files(submission: Submission) -> dict[str, set[str]]:
    return {
        locator.modifier: {file.path.name for file in cm.files}
        for locator, cm in submission.calculations
    }


def test_static_calculations_are_found(tmp_path):
    make_files(
        tmp_path,
        ["INCAR.relax2", "vasprun.xml.relax2", "INCAR.static", "vasprun.xml.static"],
    )
    submission = Submission.from_paths([tmp_path])
    assert [loc.modifier for loc, _ in submission.calculations] == ["relax2", "static"]


def test_shared_files_are_in_every_calculation(tmp_path):
    make_files(
        tmp_path,
        [
            "INCAR.relax1",
            "INCAR.relax2",
            "vasprun.xml.relax1",
            "vasprun.xml.relax2",
            "POTCAR",
            "INCAR.orig",
            "custodian.json",
            "CHGCAR",
        ],
    )
    files = calculation_files(Submission.from_paths([tmp_path]))
    assert set(files) == {"relax1", "relax2"}
    assert "POTCAR" in files["relax1"] and "POTCAR" in files["relax2"]
    assert "custodian.json" in files["relax1"] and "custodian.json" in files["relax2"]
    # the original inputs are the first calculation's, the outputs the last's
    assert "INCAR.orig" in files["relax1"] and "INCAR.orig" not in files["relax2"]
    assert "CHGCAR" in files["relax2"] and "CHGCAR" not in files["relax1"]


def test_calculations_without_output_are_found(tmp_path):
    make_files(tmp_path / "not_run", ["INCAR", "POSCAR", "KPOINTS", "POTCAR"])
    make_files(
        tmp_path / "multi_calc", ["INCAR.relax1", "vasprun.xml.relax1", "INCAR.relax2"]
    )
    submission = Submission.from_paths([tmp_path])
    assert {
        (locator.path.name, locator.modifier) for locator, _ in submission.calculations
    } == {("not_run", "standard"), ("multi_calc", "relax1"), ("multi_calc", "relax2")}


class TestAddingFiles:
    def test_file_with_unrecognized_name_is_rejected(self, tmp_path):
        make_files(tmp_path, ["INCAR", "vasprun.xml", "CHGCAR.bak.gz"])
        with pytest.raises(
            EmmetCliError, match="'bak'.*Rename the file, or leave it out"
        ):
            Submission.from_paths([tmp_path / "CHGCAR.bak.gz"])
        with pytest.raises(EmmetCliError, match="not a recognized VASP file"):
            Submission.from_paths([make_files(tmp_path, ["notes.txt"]) / "notes.txt"])

    def test_nothing_is_added_if_a_file_is_rejected(self, tmp_path):
        make_files(tmp_path / "first", ["INCAR", "vasprun.xml"])
        make_files(tmp_path / "second", ["INCAR", "vasprun.xml", "OUTCAR.old"])
        submission = Submission.from_paths([tmp_path / "first"])
        before = submission.model_dump()

        with pytest.raises(EmmetCliError, match="'old'"):
            submission.add_to(
                [tmp_path / "second" / "INCAR", tmp_path / "second" / "OUTCAR.old"]
            )
        assert submission.model_dump() == before

    def test_unrecognized_files_in_directories_are_skipped(self, tmp_path):
        make_files(tmp_path, ["INCAR", "vasprun.xml", "CHGCAR.bak.gz", "OUTCAR.old"])
        files = calculation_files(Submission.from_paths([tmp_path]))
        assert files == {"standard": {"INCAR", "vasprun.xml"}}

    def test_a_file_is_added_to_the_calculations_it_belongs_to(self, tmp_path):
        make_files(
            tmp_path,
            [
                "INCAR.relax1",
                "INCAR.relax2",
                "vasprun.xml.relax1",
                "vasprun.xml.relax2",
                "POTCAR",
                "KPOINTS.relax2",
            ],
        )
        # a shared file is part of each calculation
        files = calculation_files(Submission.from_paths([tmp_path / "POTCAR"]))
        assert files == {"relax1": {"POTCAR"}, "relax2": {"POTCAR"}}

        # a file with a suffix is part of its calculation, and only that file is added
        files = calculation_files(Submission.from_paths([tmp_path / "KPOINTS.relax2"]))
        assert files == {"relax2": {"KPOINTS.relax2"}}

        # static is a calculation suffix
        make_files(tmp_path, ["vasprun.xml.static"])
        files = calculation_files(
            Submission.from_paths([tmp_path / "vasprun.xml.static"])
        )
        assert files == {"static": {"vasprun.xml.static"}}


class TestCalculationSuffixes:
    def test_default_suffixes_are_saved(self, tmp_path):
        make_files(tmp_path, ["INCAR", "vasprun.xml"])
        submission = Submission.from_paths([tmp_path])
        loaded = Submission.model_validate(json.loads(submission.model_dump_json()))
        assert loaded.calc_suffixes == submission.calc_suffixes
        assert "static" in loaded.calc_suffixes

    def test_custom_suffixes_are_used_and_kept(self, tmp_path):
        make_files(
            tmp_path,
            ["INCAR.nscf", "vasprun.xml.nscf", "INCAR.uniform", "vasprun.xml.uniform"],
        )
        submission = Submission.from_paths(
            [tmp_path], calc_suffixes=("nscf", "uniform")
        )
        assert [loc.modifier for loc, _ in submission.calculations] == [
            "nscf",
            "uniform",
        ]
        loaded = Submission.model_validate(json.loads(submission.model_dump_json()))
        assert loaded.calc_suffixes == ("nscf", "uniform")

        # files are added with the same suffixes, and the default ones no longer apply
        loaded.add_to([make_files(tmp_path, ["KPOINTS.nscf"]) / "KPOINTS.nscf"])
        assert "KPOINTS.nscf" in calculation_files(loaded)["nscf"]
        with pytest.raises(EmmetCliError, match="'relax1'"):
            loaded.add_to([make_files(tmp_path, ["KPOINTS.relax1"]) / "KPOINTS.relax1"])

    def test_staged_changes_have_the_suffixes(self, tmp_path):
        make_files(tmp_path, ["INCAR.nscf", "vasprun.xml.nscf"])
        submission = Submission.from_paths([tmp_path], calc_suffixes=("nscf",))
        changes = submission.get_submission_changes(
            None, submission.calculations, calc_suffixes=submission.calc_suffixes
        )
        assert changes.calc_suffixes == ("nscf",)
