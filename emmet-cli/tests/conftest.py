import os
from pathlib import Path
from uuid import uuid4
from click.testing import CliRunner
from emmet.cli.state_manager import StateManager
from emmet.cli.submission import Submission
from emmet.cli.submit import _create_submission
from emmet.cli.task_manager import TaskManager
from emmet.core.vasp.validation import ValidationDoc
from emmet.core.testing_utils import DataArchive

import pytest


@pytest.fixture
def cli_runner(task_manager):
    """Fixture that provides a CliRunner with proper context setup."""

    def invoke_wrapper(command, *args, **kwargs):
        runner = CliRunner()
        if "obj" not in kwargs:
            kwargs["obj"] = {"task_manager": task_manager}
        return runner.invoke(command, *args, **kwargs)

    return invoke_wrapper


def wait_for_task_completion_and_assert_status(result, task_manager, status):
    task_id = result.output.split("\n")[0].split()[-1]
    final_status = task_manager.wait_for_task_completion(task_id, timeout=10)
    assert final_status["status"] == status
    return final_status


def wait_for_task_completion_and_assert_success(result, task_manager):
    return wait_for_task_completion_and_assert_status(result, task_manager, "completed")


@pytest.fixture
def temp_state_dir(tmp_path):
    """Creates a temporary directory for state files."""
    state_dir = tmp_path / "test_emmet"
    return state_dir


@pytest.fixture
def task_manager(state_manager, temp_state_dir):
    """Creates a TaskManager instance with a temporary state directory."""
    return TaskManager(
        state_manager=state_manager,
        daemon_log=temp_state_dir / "task_manager_daemon.log",
    )


@pytest.fixture
def inline_task_manager(task_manager, monkeypatch):
    """Run task bodies inline while preserving task status transitions."""

    def start_task(func, *args, **kwargs):
        task_id = str(uuid4())
        task_manager._update_task_status(
            task_id,
            "running",
            additional_data={"started_at": task_manager._get_current_timestamp()},
        )
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            task_manager._update_task_status(task_id, "failed", error=str(exc))
        else:
            task_manager._update_task_status(task_id, "completed", result=result)
        return task_id

    monkeypatch.setattr(task_manager, "start_task", start_task)
    return task_manager


@pytest.fixture
def state_manager(temp_state_dir):
    """Creates a StateManager instance with a temporary state directory."""
    return StateManager(state_dir=temp_state_dir)


@pytest.fixture(scope="session")
def tmp_dir(tmp_path_factory):
    directory_structure = {
        "./neb_calc/00/": ["INCAR.gz", "KPOINTS", "POSCAR.gz"],
        "./neb_calc/01/": [
            "INCAR.gz",
            "CHGCAR",
            "CONTCAR.gz",
            "KPOINTS",
            "OUTCAR",
            "POSCAR.gz",
            "POTCAR.bz2",
            "vasprun.xml",
            "GARBAGE",
        ],
        "./neb_calc/02/": ["INCAR.gz", "KPOINTS", "POSCAR.gz"],
        "neb_calc": ["INCAR.gz", "KPOINTS", "POSCAR.gz", "POTCAR.lzma"],
        "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001": [
            "AECCAR0.bz2",
            "LOCPOT.gz",
            "CONTCAR.relax1",
            "OUTCAR.relax1",
            "vasprun.xml.relax1",
            "POSCAR.T=300.gz",
            "POSCAR.T=1000.gz",
        ],
    }
    for idx in range(1, 3):
        directory_structure[
            "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001"
        ].extend(
            [
                f"INCAR.relax{idx}",
                f"INCAR.orig.relax{idx}",
                f"POSCAR.relax{idx}",
                f"POSCAR.orig.relax{idx}",
                f"POTCAR.relax{idx}",
                f"POTCAR.orig.relax{idx}",
            ]
        )
    tmp_dir = tmp_path_factory.mktemp("neb_test_dir")

    for calc_dir, files in directory_structure.items():
        p = tmp_dir / calc_dir
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        for f in files:
            (p / f).touch()

    return tmp_dir


@pytest.fixture()
def sub_file(tmp_dir, cli_runner, tmp_path_factory, task_manager):
    result = _create_submission(paths=[str(tmp_dir)])
    matches = result[1]

    sub = Submission.load(Path(matches))

    # clean up side-effect of calling create
    os.remove(matches)

    output_file = tmp_path_factory.mktemp("sub_test_dir") / "sub.json"
    sub.save(output_file)

    return str(output_file)


@pytest.fixture(scope="session")
def validation_test_path():
    return (
        Path(__file__)
        .parent.parent.parent.joinpath("test_files/vasp/Si_uniform.json.gz")
        .resolve()
    )


@pytest.fixture()
def validation_sub_file(validation_test_path, tmp_path_factory):
    with DataArchive.extract(validation_test_path) as dir_name:
        result = _create_submission(paths=[str(dir_name)])
        matches = result[1]

        sub = Submission.load(Path(matches))

        # clean up side-effect of calling create
        os.remove(matches)

        output_file = tmp_path_factory.mktemp("sub_test_dir") / "validation_sub.json"
        sub.save(output_file)

        yield str(output_file)


@pytest.fixture()
def invalid_validation_sub_file(tmp_path):
    calc_dir = tmp_path / "invalid_calc"
    calc_dir.mkdir()
    for file_name in ("INCAR", "POSCAR", "POTCAR", "CONTCAR", "OUTCAR", "vasprun.xml"):
        (calc_dir / file_name).touch()

    submission = Submission.from_paths(paths=[calc_dir])
    output_file = tmp_path / "invalid_validation_sub.json"
    submission.save(output_file)
    return str(output_file)


@pytest.fixture(autouse=True)
def disable_potcar_validation(monkeypatch):
    original = ValidationDoc.from_file_metadata.__func__

    def from_file_metadata_without_potcar(cls, file_meta, **kwargs):
        kwargs["check_potcar"] = False
        return original(cls, file_meta, **kwargs)

    monkeypatch.setattr(
        ValidationDoc,
        "from_file_metadata",
        classmethod(from_file_metadata_without_potcar),
    )
