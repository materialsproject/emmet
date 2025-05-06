from pathlib import Path
from emmet.cli.submission import Submission
from emmet.cli.utils import EmmetCliError
import pytest


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


def verify_submission_calculations_against_tmp_dir_data(calculations):
    for path, cm in calculations.items():
        if path.name == "00":
            assert len(cm.files) == 3
        elif path.name == "01":
            assert len(cm.files) == 8
        elif path.name == "02":
            assert len(cm.files) == 3
        elif path.name == "neb_calc":
            assert len(cm.files) == 4
        elif path.name == "launcher_2025_02_31_0001":
            assert len(cm.files) == 19
        else:
            assert path is None


def test_from_paths(tmp_dir):
    submission = Submission.from_paths(paths=[tmp_dir])

    verify_submission_calculations_against_tmp_dir_data(submission.calculations)
    assert len(submission.calculations.keys()) == 5


def test_save_and_load(sub_file):
    # conftest already creates a saved file so re-using that
    sub = Submission.load(Path(sub_file))
    verify_submission_calculations_against_tmp_dir_data(sub.calculations)


def test_add_to(sub_file, tmp_structure):
    sub = Submission.load(Path(sub_file))

    # test adding already present paths and files
    to_add_path = []
    for p, cm in sub.calculations.items():
        if "neb_calc/01" in str(p):
            to_add_path.append(p)
        elif "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001" in str(p):
            to_add_path.append(cm.files[0].path)

    assert len(to_add_path) == 2

    added = sub.add_to(to_add_path)
    assert len(added) == 0

    # test adding new paths and files too
    to_add_path = to_add_path + list(tmp_structure.values())
    added = sub.add_to(to_add_path)
    assert len(added) == 4
    assert len(sub.calculations.keys()) == 7


def test_remove_from(sub_file, tmp_structure):
    sub = Submission.load(Path(sub_file))

    # test removing paths and files not present
    removed = sub.remove_from(tmp_structure.values())
    assert len(removed) == 0

    # test removing present paths and files too
    to_remove_path = []
    for p, cm in sub.calculations.items():
        if "neb_calc/01" in str(p):
            to_remove_path.append(p)
        elif "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001" in str(p):
            to_remove_path.append(cm.files[0].path)

    assert len(to_remove_path) == 2

    removed = sub.remove_from(to_remove_path + list(tmp_structure.values()))
    assert len(removed) == 9


def test_changed_files(sub_file):
    sub = Submission.load(Path(sub_file))
    changed = sub.get_changed_files_per_calc_path(
        sub.calculations, sub._create_refreshed_calculations()
    )
    assert len(changed) == 0
    changed = sub.get_changed_files_per_calc_path(
        sub.last_pushed(), sub._create_refreshed_calculations()
    )
    assert len(changed) == 5


def test_validate(sub_file):
    sub = Submission.load(Path(sub_file))

    assert sub.validate() is True

    # TODO: once validation is implemented check invalid and then check that staging fails this way
    # with pytest.raises(EmmetCliError) as ex_info:
    #     sub.stage_for_push()

    # assert "Submission does not pass validation" in str(ex_info.value)


def test_changed_files_to_push(sub_file):
    sub = Submission.load(Path(sub_file))

    with pytest.raises(EmmetCliError) as ex_info:
        sub.push()

    assert "Nothing is staged" in str(ex_info.value)

    changed = sub.stage_for_push()
    assert len(changed) == 37
    verify_submission_calculations_against_tmp_dir_data(sub.pending_calculations)
    changed = sub.stage_for_push()
    assert len(changed) == 37
    verify_submission_calculations_against_tmp_dir_data(sub.pending_calculations)

    sub.push()
    changed = sub.stage_for_push()
    assert len(changed) == 0
    verify_submission_calculations_against_tmp_dir_data(sub.pending_calculations)

    # check that if file changed after stage then push raises exception
