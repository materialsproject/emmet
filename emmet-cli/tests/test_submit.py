import os
from pathlib import Path
from emmet.cli.submission import Submission
from emmet.cli.submit import submit
from emmet.cli.utils import EmmetCliError
from conftest import wait_for_task_completion_and_assert_success


def test_create(tmp_dir, cli_runner, task_manager):
    result = cli_runner(submit, ["create"])

    assert result.exit_code != 0
    assert isinstance(result.exception, EmmetCliError)
    assert (
        "Must provide at least one file or directory path to include in submission"
        in str(result.exception)
    )

    result = cli_runner(submit, ["create", str(tmp_dir)])

    assert result.exit_code == 0
    assert "Submission creation started." in result.output

    final_status = wait_for_task_completion_and_assert_success(result, task_manager)

    # clean up side-effect of calling create
    matches = final_status["result"][1]
    assert "submission-" in matches
    os.remove(matches)


def test_add_to(sub_file, cli_runner, task_manager, tmp_path_factory):
    result = cli_runner(submit, ["add-to", sub_file])

    assert result.exit_code != 0
    assert isinstance(result.exception, EmmetCliError)
    assert (
        "Must provide at least one file or directory path to add to the submission"
        in str(result.exception)
    )

    sub = Submission.load(Path(sub_file))
    it = iter(sub.calculations)
    while (path_to_add_from := next(it), None) and "neb_calc/01" not in str(
        path_to_add_from
    ):
        pass

    result = cli_runner(submit, ["add-to", sub_file, str(path_to_add_from)])

    assert result.exit_code == 0
    assert "Adding files started." in result.output

    final_status = wait_for_task_completion_and_assert_success(result, task_manager)

    # clean up side-effect of calling create
    matches = final_status["result"]
    assert len(matches) == 0

    # Create a new temp directory with some test files
    new_dir = tmp_path_factory.mktemp("additional_files")
    test_files = ["INCAR", "POSCAR", "OUTCAR"]
    for f in test_files:
        (new_dir / f).touch()

    result = cli_runner(submit, ["add-to", sub_file, str(new_dir)])

    assert result.exit_code == 0
    assert "Adding files started." in result.output

    final_status = wait_for_task_completion_and_assert_success(result, task_manager)

    # Verify the files were added
    matches = final_status["result"]
    assert len(matches) == len(test_files)
    for match in matches:
        assert any(test_file in match for test_file in test_files)


def test_remove_from(sub_file, cli_runner, task_manager):
    result = cli_runner(submit, ["remove-from", sub_file])

    assert result.exit_code != 0
    assert isinstance(result.exception, EmmetCliError)
    assert (
        "Must provide at least one file or directory path to remove from the submission"
        in str(result.exception)
    )

    sub = Submission.load(Path(sub_file))
    it = iter(sub.calculations)
    while (path_to_remove := next(it), None) and "neb_calc/01" not in str(
        path_to_remove
    ):
        pass

    result = cli_runner(submit, ["remove-from", sub_file, str(path_to_remove)])

    assert result.exit_code == 0
    assert "Removing files started." in result.output

    final_status = wait_for_task_completion_and_assert_success(result, task_manager)

    # Verify the files were added
    matches = final_status["result"]
    assert len(matches) == 8
    assert all(str(path_to_remove) in match for match in matches)


def test_validate(sub_file, cli_runner, task_manager):
    result = cli_runner(submit, ["validate", sub_file])

    assert result.exit_code == 0
    assert "Validation started." in result.output
    final_status = wait_for_task_completion_and_assert_success(result, task_manager)
    assert final_status["result"] == True

    # TODO: add test that fails validation when add implementation
    # TODO: add test for check_all parameter values when add implementation


def test_push(sub_file, cli_runner, task_manager):
    result = cli_runner(submit, ["push", sub_file])

    assert result.exit_code == 0
    assert "Push started." in result.output

    final_status = wait_for_task_completion_and_assert_success(result, task_manager)
    assert final_status["result"][0] == True

    # TODO: add test that for failing cases
