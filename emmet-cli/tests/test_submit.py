import os
import pytest
from pathlib import Path
from emmet.cli.submission import Submission
from emmet.cli.submit import (
    submit,
    _add_to_submission,
    _create_submission,
    _remove_from_submission,
)
from emmet.cli.utils import EmmetCliError
from conftest import (
    wait_for_task_completion_and_assert_success,
)


def test_create(tmp_dir, cli_runner, task_manager):
    result = cli_runner(submit, ["create"])

    assert result.exit_code != 0
    assert isinstance(result.exception, EmmetCliError)
    assert (
        "Must provide at least one file or directory path to include in submission"
        in str(result.exception)
    )

    result = _create_submission(paths=[str(tmp_dir)])

    # clean up side-effect of calling create
    matches = result[1]
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
    # Find the first calculation with neb_calc/01 in its path
    path_to_add_from = next(
        (loc.path for loc, _ in sub.calculations if "neb_calc/01" in str(loc.path)),
        None,
    )
    assert path_to_add_from is not None

    result = _add_to_submission(
        submission_path=Path(sub_file), paths=[str(path_to_add_from)]
    )

    # clean up side-effect of calling create
    matches = result
    assert len(matches) == 0

    # Create a new temp directory with some test files
    new_dir = tmp_path_factory.mktemp("additional_files")
    test_files = ["INCAR", "POSCAR", "OUTCAR"]
    for f in test_files:
        (new_dir / f).touch()

    result = _add_to_submission(submission_path=Path(sub_file), paths=[str(new_dir)])
    # Verify the files were added
    matches = result
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
    # Find the first calculation with neb_calc/01 in its path
    path_to_remove = next(
        (loc.path for loc, _ in sub.calculations if "neb_calc/01" in str(loc.path)),
        None,
    )
    assert path_to_remove is not None

    result = _remove_from_submission(
        submission_path=Path(sub_file), paths_to_remove=[str(path_to_remove)]
    )

    matches = result
    assert len(matches) == 8
    assert all(str(path_to_remove) in match for match in matches)


def test_validate_success(validation_sub_file, cli_runner, inline_task_manager):
    result = cli_runner(submit, ["validate", validation_sub_file])

    assert result.exit_code == 0
    assert "Validation started." in result.output
    final_status = wait_for_task_completion_and_assert_success(
        result, inline_task_manager
    )
    assert final_status["result"] is True

    submission = Submission.load(Path(validation_sub_file))
    assert all(cm.calc_valid is True for _, cm in submission.calculations)
    assert all(not cm.calc_validation_errors for _, cm in submission.calculations)


def test_validate_failure(invalid_validation_sub_file, cli_runner, inline_task_manager):
    result = cli_runner(submit, ["validate", invalid_validation_sub_file])

    assert result.exit_code == 0
    assert "Validation started." in result.output
    final_status = wait_for_task_completion_and_assert_success(
        result, inline_task_manager
    )
    assert final_status["result"] is False

    submission = Submission.load(Path(invalid_validation_sub_file))
    assert any(
        cm.calc_valid is False and cm.calc_validation_errors
        for _, cm in submission.calculations
    )


@pytest.mark.skip(reason="Push coverage is deferred to issue #1486.")
def test_push(validation_sub_file, cli_runner, task_manager):
    result = cli_runner(submit, ["push", validation_sub_file])

    assert result.exit_code == 0
    assert "Push started." in result.output
