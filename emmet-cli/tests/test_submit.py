import os
from pathlib import Path
from click.testing import CliRunner
from emmet.cli.submission import Submission
from emmet.cli.submit import submit
from emmet.cli.utils import EmmetCliError


def test_create(tmp_dir):
    runner = CliRunner()
    result = runner.invoke(submit, ["create"])

    assert result.exit_code != 0
    assert isinstance(result.exception, EmmetCliError)
    assert (
        "Must provide at least one file or directory path to include in submission"
        in str(result.exception)
    )

    runner = CliRunner()
    result = runner.invoke(submit, ["create", str(tmp_dir)])

    assert result.exit_code == 0
    assert "wrote submission output to" in result.output

    # clean up side-effect of calling create
    matches = [word for word in result.output.split() if "submission-" in word]
    assert len(matches) == 1
    os.remove(matches[0])


def test_add_to(sub_file):
    runner = CliRunner()
    result = runner.invoke(submit, ["add-to", sub_file])

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

    result = runner.invoke(submit, ["add-to", sub_file, str(path_to_add_from)])

    assert result.exit_code == 0
    assert result.output.count(str(path_to_add_from)) == 0


def test_remove_from(sub_file):
    runner = CliRunner()
    result = runner.invoke(submit, ["remove-from", sub_file])

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

    result = runner.invoke(submit, ["remove-from", sub_file, str(path_to_remove)])

    assert result.exit_code == 0
    assert result.output.count(str(path_to_remove)) == 8


def test_validate(sub_file):
    runner = CliRunner()
    result = runner.invoke(submit, ["validate", sub_file])

    assert result.exit_code == 0
    assert "passed validation" in str(result.output)

    # TODO: add test that fails validation when add implementation


def test_push(sub_file):
    runner = CliRunner()
    result = runner.invoke(submit, ["push", sub_file])

    assert result.exit_code == 0
    assert "Successfuly updated submission in" in str(result.output)

    # TODO: add test that for failing cases
