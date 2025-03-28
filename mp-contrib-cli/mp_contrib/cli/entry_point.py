import logging
import sys
import click

from mp_contrib.cli.submit import submit
from mp_contrib.cli.utils import MPContribCliError

logger = logging.getLogger("mp_contrib_cli")

@click.group()
@click.option("--verbose", is_flag=True, help="Show debug messages.")
@click.version_option()
@click.pass_context
def mp_contrib(ctx, verbose):
    """Command line interface for MP contributions"""

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def safe_entry_point():
    try:
        mp_contrib()
    except MPContribCliError as e:
        click.secho(str(e), fg="red")
    except Exception as e:
        logger.info(e, exc_info=True)

mp_contrib.add_command(submit)

