import logging
import sys
import click

from emmet.cli.submit import submit
from emmet.cli.utils import EmmetCliError

logger = logging.getLogger("emmet")


@click.group()
@click.option("--verbose", is_flag=True, help="Show debug messages.")
@click.version_option()
@click.pass_context
def emmet(ctx, verbose):
    """Command line interface for Emmet"""

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def safe_entry_point():
    try:
        emmet()
    except EmmetCliError as e:
        click.secho(str(e), fg="red")
    except Exception as e:
        logger.info(e, exc_info=True)

emmet.add_command(submit)
