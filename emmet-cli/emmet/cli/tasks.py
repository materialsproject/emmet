import click
import logging
from uuid import UUID

from emmet.cli.utils import EmmetCliError

logger = logging.getLogger("emmet")


@click.group()
@click.pass_context
def tasks(ctx: click.Context) -> None:
    """Commands for managing background tasks."""
    pass


@tasks.command()
@click.argument("task_id", type=str)
@click.pass_context
def status(ctx: click.Context, task_id: str) -> None:
    """Check the status of a task."""
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        raise EmmetCliError(f"Invalid task ID: {task_id}")

    task_manager = ctx.obj["task_manager"]
    task_status = task_manager.get_task_status(str(task_uuid))

    if task_status["status"] == "not_found":
        click.echo(f"Task {task_id} not found")
        return

    if task_status.get("error"):
        click.secho(f"Task {task_id} failed: {task_status['error']}", fg="red")
    elif "completed_at" in task_status:
        click.secho(
            f"Task {task_id} completed at {task_status['completed_at']}", fg="green"
        )
        if "result" in task_status:
            click.echo(f"Result: {task_status['result']}")
    else:
        click.echo(
            f"Task {task_id} is still running (started at {task_status['started_at']})"
        )


@tasks.command()
@click.pass_context
def list(ctx: click.Context) -> None:
    """List all tasks."""
    task_manager = ctx.obj["task_manager"]
    tasks = task_manager.state_manager.get("tasks", {})

    if not tasks:
        click.echo("No tasks found")
        return

    for task_id, task in tasks.items():
        status = "✓" if "completed_at" in task else "⋯"
        if "error" in task:
            status = "✗"

        started = task["started_at"]
        completed = task.get("status", "running")

        # fmt: off
        color = (
            "green"
            if "completed_at" in task and "error" not in task
            else "red"
            if "error" in task
            else "yellow"
        )
        # fmt: on
        click.secho(f"{status} Task {task_id}", fg=color)
        click.echo(f"   Started: {started}")
        click.echo(f"   Status:  {completed}")
        if "error" in task:
            click.echo(f"   Error:   {task['error']}")
        click.echo("")


@tasks.command()
@click.argument("task_id", type=str)
@click.option(
    "--timeout", type=float, default=None, help="Maximum time to wait in seconds"
)
@click.pass_context
def wait(ctx: click.Context, task_id: str, timeout: float | None) -> None:
    """Wait for a task to complete."""
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        raise EmmetCliError(f"Invalid task ID: {task_id}")

    task_manager = ctx.obj["task_manager"]
    status = task_manager.wait_for_task_completion(str(task_uuid), timeout=timeout)

    if status["status"] == "running" and timeout:
        click.echo(f"Task {task_id} did not complete within {timeout} seconds")
        return
    elif status["status"] == "not_found":
        click.echo(f"Task {task_id} not found")
        return

    if "error" in status:
        click.secho(f"Task {task_id} failed: {status['error']}", fg="red")
    else:
        click.secho(f"Task {task_id} completed successfully", fg="green")
        if "result" in status:
            click.echo(f"Result: {status['result']}")


@tasks.command()
@click.pass_context
def clean(ctx: click.Context) -> None:
    """Clean up completed tasks."""
    task_manager = ctx.obj["task_manager"]
    task_manager.cleanup_finished_tasks()
    click.echo("Cleaned up completed tasks")


@tasks.command()
@click.argument("task_id", type=str)
@click.option(
    "--force", "-f", is_flag=True, help="Force termination without confirmation"
)
@click.pass_context
def terminate(ctx: click.Context, task_id: str, force: bool) -> None:
    """Terminate a running task."""
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        raise EmmetCliError(f"Invalid task ID: {task_id}")

    task_manager = ctx.obj["task_manager"]
    task_status = task_manager.get_task_status(str(task_uuid))

    if task_status["status"] == "not_found":
        click.echo(f"Task {task_id} not found")
        return

    if task_status["status"] != "running":
        click.echo(f"Task {task_id} is not running (status: {task_status['status']})")
        return

    if not force and not click.confirm(
        f"Are you sure you want to terminate task {task_id}?"
    ):
        click.echo("Operation cancelled")
        return

    status = task_manager.terminate_task(str(task_uuid))
    if status["status"] == "terminated":
        click.secho(f"Task {task_id} has been terminated", fg="yellow")
    else:
        click.secho(f"Failed to terminate task {task_id}", fg="red")
