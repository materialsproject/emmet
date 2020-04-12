import os
import logging
import click

from emmet.cli.utils import get_vasp_dirs


logger = logging.getLogger("emmet")


@click.group()
@click.option(
    "-d",
    "--directory",
    metavar="DIR",
    required=True,
    help="Directory with VASP launchers.",
)
@click.option(
    "-m", "nmax", default=10, show_default=True, help="Maximum #directories to walk."
)
@click.option(
    "-p", "pattern", metavar="PATTERN", help="Only include sub-paths matching pattern."
)
@click.pass_context
def hpss(ctx, directory, nmax, pattern):
    """Long-term HPSS storage"""
    ctx.obj["DIRECTORY"] = os.path.abspath(os.path.realpath(directory))
    ctx.obj["NMAX"] = nmax
    ctx.obj["PATTERN"] = pattern


@hpss.command()
@click.pass_context
def prep(ctx):
    """Prepare directory for HPSS"""
    counter = None  # catch empty iterator
    for counter, _ in enumerate(
        get_vasp_dirs(ctx.obj["DIRECTORY"], ctx.obj["PATTERN"], ctx.obj["RUN"])
    ):
        if counter == ctx.obj["NMAX"] - 1:
            break

    if counter is not None:
        logger.info(f"Prepared {counter+1} VASP calculation(s).")
    else:
        logger.error("No VASP calculations found.")
