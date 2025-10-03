import logging
import sys
import click
from pathlib import Path

from emmet.cli.submit import submit
from emmet.cli.tasks import tasks
from emmet.cli.utils import EmmetCliError
from emmet.cli.state_manager import StateManager
from emmet.cli.task_manager import TaskManager

logger = logging.getLogger("emmet")


@click.group()
@click.option("--verbose", is_flag=True, help="Show debug messages.")
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False),
    default=str(Path.home() / ".emmet"),
    help="Directory to store state files.",
)
@click.option(
    "--running-status-update-interval",
    type=int,
    default=30,
    help="Interval in seconds between task status updates. Defaults to 30 seconds.",
)
@click.version_option()
@click.pass_context
def emmet(
    ctx: click.Context,
    verbose: bool,
    state_dir: str,
    running_status_update_interval: int,
) -> None:
    """Command line interface for Emmet"""

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    state_manager = StateManager(Path(state_dir))
    task_manager = TaskManager(
        state_manager=state_manager,
        running_status_update_interval=running_status_update_interval,
    )

    # Store in context for access by subcommands
    ctx.ensure_object(dict)
    ctx.obj["state_manager"] = state_manager
    ctx.obj["task_manager"] = task_manager


def safe_entry_point() -> None:
    try:
        emmet()
    except EmmetCliError as e:
        click.secho(str(e), fg="red")
    except Exception as e:
        logger.info(e, exc_info=True)


# Add commands
emmet.add_command(submit)
emmet.add_command(tasks)
