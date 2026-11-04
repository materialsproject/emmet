"""Test the parse command, which wraps the driver."""

import json
import warnings
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

from emmet.cli.legacy import tasks as tasks_module
from emmet.cli.legacy.entry_point import emmet_legacy
from emmet.core.vasp.parse import DEFAULT_VOLUMETRIC_TYPES, ParsePolicy

from conftest import snapshot

warnings.filterwarnings("ignore")


@pytest.fixture(autouse=True)
def in_process_cluster(monkeypatch):
    """Use a cluster of threads, which is quick to start, for the command."""
    from distributed import Client, LocalCluster

    def make_client(address=None, file=None, nworkers=None):
        cluster = LocalCluster(
            n_workers=1, threads_per_worker=2, processes=False, dashboard_address=None
        )
        return Client(cluster)

    monkeypatch.setattr(tasks_module, "make_client", make_client)


@pytest.fixture(autouse=True)
def github(monkeypatch, tmp_path):
    """The group logs in to GitHub with --run, and tracks the command in an issue.

    That is how production is tracked, and is not what is tested here, so
    GitHub is replaced with a mock, which is returned to see what was tracked.
    """
    from unittest.mock import MagicMock

    from emmet.cli.legacy import entry_point

    home = tmp_path / "home"
    home.mkdir()
    (home / ".emmet_credentials").write_text("token\n")
    monkeypatch.setenv("HOME", str(home))

    mock = MagicMock()
    mock.create_gist.return_value.id = "gist-id"
    monkeypatch.setattr(entry_point, "GitHub", lambda *args, **kwargs: mock)
    return mock


def invoke(launchers: Path, *args: str, run: bool = False, **kwargs):
    """Run `emmet-legacy [--run] tasks -d <launchers> parse ...`."""
    group_args = ["--run", "--issue", "1"] if run else []
    return CliRunner().invoke(
        emmet_legacy,
        [*group_args, "tasks", "-d", str(launchers), "-m", "100", *args],
        **kwargs,
    )


def test_dry_run_only_reports(launchers, tmp_path, caplog):
    output = tmp_path / "out"
    before = snapshot(launchers)
    with caplog.at_level("INFO", logger="emmet"):
        result = invoke(
            launchers, "-p", "block_*", "parse", "--output-dir", str(output)
        )

    assert result.exit_code == 0, result.output
    assert not output.exists()
    assert snapshot(launchers) == before

    log = caplog.text
    assert "3 launcher(s), 4 calculation(s) to parse" in log
    assert "Identifiers: aaaaaaab to aaaaaaae" in log
    assert "Layouts: 2 single, 1 suffixed" in log
    assert "Would parse 4 calculation(s)" in log and "Nothing was written" in log


def test_dry_run_needs_nothing(launchers, caplog):
    """A dry run needs no output directory, scheduler or Mongo."""
    with caplog.at_level("INFO", logger="emmet"):
        result = invoke(launchers, "-p", "block_*", "parse")
    assert result.exit_code == 0, result.output
    assert "4 calculation(s) to parse" in caplog.text


def test_run(launchers, tmp_path, caplog, github):
    output = tmp_path / "out"
    before = snapshot(launchers)
    with caplog.at_level("INFO", logger="emmet"):
        result = invoke(
            launchers,
            "-p",
            "block_*",
            "parse",
            "--output-dir",
            str(output),
            "--chunk-size",
            "2",
            run=True,
        )
    assert result.exit_code == 0, result.output
    # nothing in the launchers is changed, not even their files' compression
    assert snapshot(launchers) == before

    tasks = pq.read_table(output / "tasks").to_pylist()
    assert sorted(t["task_id"] for t in tasks) == ["aaaaaaab", "aaaaaaac", "aaaaaaad"]
    # the batch id and tags default to the name of the directory
    assert {t["batch_id"] for t in tasks} == {"launchers"}
    assert all("launchers" in t["tags"] for t in tasks)
    assert pq.read_table(output / "manifest").num_rows == 4
    assert "parsed 4 calculation(s)" in caplog.text
    # the command is tracked in the issue, as COMPLETED
    comment = github.issue.return_value.create_comment.call_args_list[-1].args[0]
    assert "COMPLETED" in comment and "tasks parse" in comment


def test_run_needs_an_output_directory(launchers):
    result = invoke(launchers, "-p", "block_*", "parse", run=True)
    assert result.exit_code != 0
    assert (
        "Need --output-dir" in str(result.exception)
        or "Need --output-dir" in result.output
    )


def test_policy_options(launchers, tmp_path):
    output = tmp_path / "out"
    result = invoke(
        launchers,
        "-p",
        "block_*",
        "parse",
        "--output-dir",
        str(output),
        "--no-bandstructure",
        "--no-projections",
        run=True,
    )
    assert result.exit_code == 0, result.output
    tables = {p.name for p in output.iterdir()}
    assert "total-dos" in tables
    assert not tables & {"bandstructures", "projected-bandstructures", "projected-dos"}

    output = tmp_path / "out-2"
    result = invoke(
        launchers,
        "-p",
        "block_*",
        "parse",
        "--output-dir",
        str(output),
        "--no-dos",
        "--no-bandstructure",
        run=True,
    )
    assert result.exit_code == 0, result.output
    assert {p.name for p in output.iterdir()} == {"tasks", "trajectories", "manifest"}


def test_chg_and_pot_are_not_stored_unless_asked_for():
    policy = tasks_module._make_policy((), False, False, False, False)
    assert policy == ParsePolicy()
    assert policy.wants_volumetric("CHGCAR") and policy.wants_volumetric("LOCPOT")
    assert not policy.wants_volumetric("CHG") and not policy.wants_volumetric("POT")

    # not giving the option must not mean every type
    assert tasks_module._make_policy((), True, True, True, True).volumetric_types == (
        DEFAULT_VOLUMETRIC_TYPES
    )

    asked_for = tasks_module._make_policy(
        ("CHG", "POT", "CHGCAR"), False, False, False, False
    )
    for file_type in ("CHG", "POT", "CHGCAR"):
        assert asked_for.wants_volumetric(file_type)
    assert not asked_for.wants_volumetric("LOCPOT")


def test_unknown_volumetric_file(launchers, tmp_path):
    result = invoke(launchers, "parse", "-s", "WAVECAR")
    assert result.exit_code != 0
    assert "Unknown volumetric file types" in str(result.exception)


def test_identifier_file(launchers, tmp_path):
    output = tmp_path / "out"
    ids = tmp_path / "ids.json"
    ids.write_text(
        json.dumps(
            {
                "launcher_single": "mp-10",
                "launcher_legacy/relax1": "mp-20",
                "launcher_legacy/relax2": "mp-21",
            }
        )
    )
    result = invoke(
        launchers,
        "-p",
        "block_*",
        "parse",
        "--output-dir",
        str(output),
        "--task-ids",
        str(ids),
        run=True,
    )
    assert result.exit_code == 0, result.output
    from emmet.cli.legacy.parse_driver import normalize_identifier

    assert sorted(pq.read_table(output / "tasks")["task_id"].to_pylist()) == sorted(
        normalize_identifier(i) for i in (10, 20, 21)
    )
    # the broken launcher is not in the file, so it is not parsed
    assert pq.read_table(output / "manifest").num_rows == 3


def test_invalid_batch_id(launchers):
    result = invoke(launchers, "parse", "--batch-id", "not valid!")
    assert result.exit_code != 0
    assert "Invalid characters in the batch id" in str(result.exception)


def test_bad_delta_option(launchers):
    result = invoke(launchers, "parse", "--delta-option", "novalue")
    assert "KEY=VALUE" in str(result.exception)


def test_parsers_is_disabled(launchers):
    result = invoke(launchers, "parsers")
    assert result.exit_code != 0
    assert "parsers is disabled" in str(result.exception)


def test_no_database_is_needed(launchers):
    """The parse command works without the --spec-or-dbfile of the group."""
    result = invoke(launchers, "-p", "block_*", "parse")
    assert result.exit_code == 0, result.output
