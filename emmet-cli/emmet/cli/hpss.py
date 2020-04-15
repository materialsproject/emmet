import os
import logging
import click
import shlex
import subprocess

from collections import defaultdict
from hpsspy import HpssOSError
from hpsspy.os.path import isfile
from emmet.cli.utils import get_vasp_dirs, EmmetCliError
from emmet.cli.decorators import sbatch


logger = logging.getLogger("emmet")


@click.group()
@click.option(
    "-d",
    "--directory",
    required=True,
    help="Directory with VASP launchers.",
)
@click.option(
    "-m", "--nmax", show_default=True, default=10, help="Maximum #directories to walk."
)
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
        msg = f"Prepared {counter+1} VASP calculation(s)."
        logger.info(msg)
    else:
        msg = "No VASP calculations found."
        logger.error(msg)

    return msg


@hpss.command()
@sbatch
def backup():
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    nmax = ctx.parent.params["nmax"]
    directory = ctx.parent.params["directory"]
    pattern = ctx.parent.params["pattern"]
    prefix = "block_"

    if os.sep in pattern:
        raise EmmetCliError(f"Nested pattern ({pattern}) not allowed!")
    elif not pattern.startswith(prefix):
        raise EmmetCliError(f"Pattern ({pattern}) only allowed to start with {prefix}!")

    block_launchers = defaultdict(list)
    with click.progressbar(get_vasp_dirs(), label="Load blocks") as bar:
        for vasp_dir in bar:
            launch_dir = prefix + vasp_dir.split(prefix, 1)[-1]
            block, launcher = launch_dir.split(os.sep, 1)
            if len(block_launchers) == nmax and block not in block_launchers:
                # already found nmax blocks. Order of launchers not guaranteed
                continue
            block_launchers[block].append(launcher)

    logger.info(f"Backing up {len(block_launchers)} block(s) ...")

    for block, launchers in block_launchers.items():
        logger.info(f"{block} with {len(launchers)} launcher(s)")
        try:
            isfile(f"garden/{block}.tar")
        except HpssOSError:
            # back up block if not in HPSS
            if run:
                os.chdir(directory)
                filelist = [os.path.join(block, l) for l in launchers]
                args = shlex.split(f"htar -M 5000000 -Phcvf garden/{block}.tar")
                nargs, nfiles = len(args), len(filelist)
                args += filelist
                args_short = args[:nargs+1] + [f"({nfiles-1} more ...)"] if nfiles > 1 else args
                logger.info(" ".join(args_short))
                process = subprocess.run(
                    args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
                )
                ret = process.returncode
                logger.log(
                    logging.ERROR if ret else logging.INFO,
                    process.stderr if ret else "\n" + process.stdout
                )
        else:
            logger.warning(f"Skipping {block} - already in HPSS")
