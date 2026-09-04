import logging
from pathlib import Path
from uuid import UUID

import click
from emmet.cli.state_manager import StateManager
from emmet.cli.submission import Submission, SubmissionUploader
from emmet.cli.upload import HttpSubmissionUploader
from emmet.cli.utils import EmmetCliError

logger = logging.getLogger("emmet")


@click.group()
@click.pass_context
def submit(ctx: click.Context) -> None:
    """Commands for managing an MP data submission."""
    pass


# eventually add something here to use a config file instead
# add an option for pattern matching
@submit.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.pass_context
def create(ctx: click.Context, paths: list[Path]) -> None:
    """Creates a new MP data submission.

    This only creates metadata about the submission. The submission will
    include all the files related to calculations recursively discovered
    in the provided directory paths. The recursive walk will not follow symlinks.

    The output will contain the metadata filename path. That path will be
    used for all other actions related to this submission."""

    if not paths:
        raise EmmetCliError(
            "Must provide at least one file or directory path to include in submission"
        )

    task_manager = ctx.obj["task_manager"]
    task_id = task_manager.start_task(_create_submission, paths)
    click.echo(f"Submission creation started. Task ID: {task_id}")
    click.echo("Use 'emmet tasks status <task_id>' to check the status")


def _create_submission(paths: list[Path]) -> tuple[str, str]:
    """Helper function to create a submission that can run in a separate process."""
    submission = Submission.from_paths(paths=paths)
    output_file = f"submission-{submission.id}.json"
    submission.save(Path(output_file))
    return str(submission.id), output_file


def _add_to_submission(submission_path: Path, paths: list[Path]) -> list[str]:
    """Helper function to add files to a submission that can run in a separate process."""
    sub = Submission.load(submission_path)
    added = sub.add_to([Path(p) for p in paths])
    sub.save(submission_path)
    return [str(f.path) for f in added]


@submit.command()
@click.argument("submission", nargs=1, type=click.Path(exists=True, dir_okay=False))
@click.argument("additional_paths", nargs=-1, type=click.Path(exists=True))
@click.pass_context
def add_to(ctx: click.Context, submission: Path, additional_paths: list[Path]) -> None:
    """Adds more files to the submission asynchronously.

    Returns a task ID that can be used to check the status."""
    if not additional_paths:
        raise EmmetCliError(
            "Must provide at least one file or directory path to add to the submission"
        )

    task_manager = ctx.obj["task_manager"]
    task_id = task_manager.start_task(
        _add_to_submission, Path(submission), additional_paths
    )
    click.echo(f"Adding files started. Task ID: {task_id}")
    click.echo("Use 'emmet tasks status <task_id>' to check the status")


def _remove_from_submission(
    submission_path: Path, paths_to_remove: list[Path]
) -> list[str]:
    """Helper function to remove files from a submission that can run in a separate process."""
    sub = Submission.load(submission_path)
    removed = sub.remove_from([Path(p) for p in paths_to_remove])
    sub.save(submission_path)
    return [str(f.path) for f in removed]


@submit.command()
@click.argument("submission", nargs=1, type=click.Path(exists=True, dir_okay=False))
@click.argument("files_to_remove", nargs=-1, type=click.Path(exists=True))
@click.pass_context
def remove_from(
    ctx: click.Context, submission: Path, files_to_remove: list[Path]
) -> None:
    """Removes files from the submission asynchronously.

    Returns a task ID that can be used to check the status."""
    if not files_to_remove:
        raise EmmetCliError(
            "Must provide at least one file or directory path to remove from the submission"
        )

    task_manager = ctx.obj["task_manager"]
    task_id = task_manager.start_task(
        _remove_from_submission, Path(submission), files_to_remove
    )
    click.echo(f"Removing files started. Task ID: {task_id}")
    click.echo("Use 'emmet tasks status <task_id>' to check the status")


def _validate_submission(submission_path: Path, check_all: bool) -> bool:
    """Helper function to validate a submission that can run in a separate process."""
    sub = Submission.load(submission_path)
    is_valid = sub.validate_submission(check_all=check_all)
    sub.save(submission_path)
    return is_valid


@submit.command()
@click.argument("submission", nargs=1, type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--check-all", is_flag=True, default=False, help="Checks every calculation."
)
@click.pass_context
def validate(ctx: click.Context, submission: Path, check_all: bool) -> None:
    """Validates a submission asynchronously.

    Returns a task ID that can be used to check the status."""
    task_manager = ctx.obj["task_manager"]
    task_id = task_manager.start_task(_validate_submission, Path(submission), check_all)
    click.echo(f"Validation started. Task ID: {task_id}")
    click.echo("Use 'emmet tasks status <task_id>' to check the status")


def _push_submission(
    submission_path: Path,
    state_dir: Path | None = None,
    uploader: SubmissionUploader | None = None,
) -> tuple[bool, str]:
    """Helper function to push a submission that can run in a separate process."""
    sub = Submission.load(submission_path)
    changes = sub.stage_for_push()
    if not changes.has_changes:
        return (
            False,
            "Files for submission have not changed since last update. Not pushing.",
        )

    if uploader is None:
        state_manager = StateManager(state_dir or Path.home() / ".emmet")
        with HttpSubmissionUploader.from_environment(state_manager) as managed_uploader:
            sub.push(managed_uploader)
    else:
        sub.push(uploader)
    sub.save(submission_path)
    return True, f"Successfully updated submission in {submission_path}"


@submit.command()
@click.argument("submission", nargs=1, type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def push(ctx: click.Context, submission: Path) -> None:
    """Pushes a submission asynchronously.

    Returns a task ID that can be used to check the status."""
    task_manager = ctx.obj["task_manager"]
    state_dir = task_manager.state_manager.state_dir
    task_id = task_manager.start_task(_push_submission, Path(submission), state_dir)
    click.echo(f"Push started. Task ID: {task_id}")
    click.echo("Use 'emmet tasks status <task_id>' to check the status")


def _submission_id_from_target(target: str) -> UUID:
    """Resolve a submission metadata path or UUID to a submission ID."""
    target_path = Path(target)
    if target_path.exists():
        if not target_path.is_file():
            raise EmmetCliError(f"Submission target is not a file: {target}")
        try:
            return Submission.load(target_path).id
        except (OSError, ValueError):
            raise EmmetCliError(
                f"Could not load submission metadata from {target}."
            ) from None
    try:
        return UUID(target)
    except ValueError:
        raise EmmetCliError(
            f"Submission target must be an existing metadata file or UUID: {target}"
        ) from None


def _echo_object_ids(label: str, object_ids: list[str]) -> None:
    click.echo(f"{label}: {len(object_ids)}")
    for object_id in object_ids:
        click.echo(f"  {object_id}")


@submit.command("contributor-status")
@click.pass_context
def contributor_status(ctx: click.Context) -> None:
    """Checks whether the current user can contribute submissions."""
    state_manager = ctx.obj["task_manager"].state_manager
    with HttpSubmissionUploader.from_environment(state_manager) as client:
        status = client.contributor_status()
    click.echo(f"Contributor status: {status}")


@submit.command("status")
@click.argument("target", nargs=1, type=str)
@click.pass_context
def submission_status(ctx: click.Context, target: str) -> None:
    """Checks remote status using a submission metadata file or UUID."""
    submission_id = _submission_id_from_target(target)
    state_manager = ctx.obj["task_manager"].state_manager
    with HttpSubmissionUploader.from_environment(state_manager) as client:
        status = client.submission_status(submission_id)
    click.echo(f"Submission {status['submission_id']}: {status['status']}")
    _echo_object_ids("Completed objects", status["completed_object_ids"])
    _echo_object_ids("In-progress objects", status["in_progress_object_ids"])
