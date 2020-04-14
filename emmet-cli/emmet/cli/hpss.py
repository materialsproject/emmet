import os
import logging
import click

from emmet.cli.utils import get_vasp_dirs, sbatch


logger = logging.getLogger("emmet")


@click.group()
@click.option(
    "-d",
    "--directory",
    required=True,
    help="Directory with VASP launchers.",
)
@click.option("-m", "--nmax", default=10, help="Maximum #directories to walk.")
@click.option(
    "-p", "--pattern", help="Only include sub-paths matching pattern."
)
def hpss(directory, nmax, pattern):
    """Long-term HPSS storage"""
    pass


@hpss.command()
@sbatch
def prep():
    """Prepare directory for HPSS"""
    ctx = click.get_current_context()
    counter = None  # catch empty iterator
    for counter, _ in enumerate(get_vasp_dirs()):
        if counter == ctx.parent.params["nmax"] - 1:
            break

    if counter is not None:
        logger.info(f"Prepared {counter+1} VASP calculation(s).")
    else:
        logger.error("No VASP calculations found.")
