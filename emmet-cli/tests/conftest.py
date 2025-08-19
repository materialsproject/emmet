import os
from pathlib import Path
from click.testing import CliRunner
from emmet.cli.state_manager import StateManager
from emmet.cli.submission import CalculationMetadata, Submission
from emmet.cli.submit import submit
from emmet.cli.task_manager import TaskManager
from emmet.core.vasp.validation import ValidationDoc

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
    final_status = task_manager.wait_for_task_completion(task_id)
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
    result = cli_runner(submit, ["create", str(tmp_dir)])

    assert result.exit_code == 0
    final_status = wait_for_task_completion_and_assert_success(result, task_manager)
    matches = final_status["result"][1]

    sub = Submission.load(Path(matches))

    # clean up side-effect of calling create
    os.remove(matches)

    output_file = tmp_path_factory.mktemp("sub_test_dir") / "sub.json"
    sub.save(output_file)

    return str(output_file)


@pytest.fixture(scope="session")
def validation_test_dir():
    return (
        Path(__file__)
        .parent.parent.parent.joinpath("test_files/vasp/Si_uniform")
        .resolve()
    )


@pytest.fixture()
def validation_sub_file(
    validation_test_dir, cli_runner, tmp_path_factory, task_manager
):
    result = cli_runner(submit, ["create", str(validation_test_dir)])

    assert result.exit_code == 0
    final_status = wait_for_task_completion_and_assert_success(result, task_manager)
    matches = final_status["result"][1]

    sub = Submission.load(Path(matches))

    # clean up side-effect of calling create
    os.remove(matches)

    output_file = tmp_path_factory.mktemp("sub_test_dir") / "validation_sub.json"
    sub.save(output_file)

    return str(output_file)


# TODO: remove this when monkeypatch tests to use fake POTCARs rather than skipping them
@pytest.fixture(autouse=True)
def patch_validate_calc(monkeypatch):
    def validate_without_checking_potcar(self, locator):
        try:
            self.refresh()
            if self.calc_valid is None:
                validator = ValidationDoc.from_file_metadata(
                    file_meta=self.files, fast=True, check_potcar=False
                )
                self.calc_valid = validator.valid
                self.calc_validation_errors = validator.reasons
        except Exception as e:
            self.calc_valid = False
            self.calc_validation_errors.append(f"Error validating calculation: {e}")
        return self.calc_valid

    # Bind it onto the class under test
    monkeypatch.setattr(
        CalculationMetadata, "validate_calculation", validate_without_checking_potcar
    )
