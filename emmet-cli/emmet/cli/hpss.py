import os
import logging
import click

from collections import defaultdict
from hpsspy.util import hsi, htar
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
    if run and not "HPSS_DIR" in os.environ:
        raise EmmetCliError("Set HPSS_DIR envvar to directory with hsi/htar binaries!")

    TMPDIR = os.path.join(os.path.expanduser("~"), '.emmet_tmp')
    if not os.path.exists(TMPDIR):
        os.mkdir(TMPDIR)
    TMPFILE = os.path.join(TMPDIR, "hsi.txt")
    if not os.path.exists(TMPFILE):
        open(TMPFILE, 'a').close()

    pattern = ctx.parent.params["pattern"]
    prefix = "block_"
    if os.sep in pattern:
        raise EmmetCliError(f"Nested pattern ({pattern}) not allowed!")
    elif not pattern.startswith(prefix):
        raise EmmetCliError(f"Pattern ({pattern}) only allowed to start with {prefix}!")

    nmax = ctx.parent.params["nmax"]
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

    # TODO get_vasp_dirs: ensure correct permissions and group ownership after gzip
    logger.info(hsi("ls", "-1", tmpdir=TMPDIR))


    #hsi -q -l matcomp ls -1 garden/${block}.tar
    #if [ $? -ne 0 ]; then
    #echo "upload new archive for ${block}"
    #htar -M 5000000 -cvf garden/${block}.tar ${block}
