import os
import shutil
import shlex
import logging
import click
import subprocess

from collections import defaultdict
from hpsspy import HpssOSError
from hpsspy.os.path import isfile
from emmet.cli.utils import get_vasp_dirs, EmmetCliError
from emmet.cli.decorators import sbatch


logger = logging.getLogger("emmet")


@click.group()
@click.option(
    "-d", "--directory", required=True, help="Source or target directory for HPSS.",
)
@click.option(
    "-m", "--nmax", show_default=True, default=10, help="Maximum number of directories."
)
@click.option("-p", "--pattern", help="Only include sub-paths matching pattern.")
def hpss(directory, nmax, pattern):
    """Long-term HPSS storage"""
    pass


@hpss.command()
@sbatch
def prep():
    """Prepare directory for HPSS"""
    ctx = click.get_current_context()
    directory = ctx.parent.params["directory"]
    counter = None  # catch empty iterator
    for counter, _ in enumerate(get_vasp_dirs()):
        if counter == ctx.parent.params["nmax"] - 1:
            break

    if counter is not None:
        logger.info(f"Prepared {counter+1} VASP calculation(s).")
    else:
        logger.error("No VASP calculations found.")

    return f"Done preparing {directory} for HPSS backup."


def run_command(args, filelist):
    # TODO deal with filelist too long
    nargs, nfiles, nshow = len(args), len(filelist), 1
    args += filelist
    args_short = (
        args[: nargs + nshow] + [f"({nfiles-1} more ...)"] if nfiles > nshow else args
    )
    logger.info(" ".join(args_short))
    popen = subprocess.Popen(args, stdout=subprocess.PIPE, universal_newlines=True)
    for stdout_line in iter(popen.stdout.readline, ""):
        yield stdout_line
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, args)


def recursive_chown(path, group):
    for dirpath, dirnames, filenames in os.walk(path):
        shutil.chown(dirpath, group=group)
        for filename in filenames:
            shutil.chown(os.path.join(dirpath, filename), group=group)


@hpss.command()
@sbatch
def backup():
    """Backup directory to HPSS"""
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

    counter = 0
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
                for line in run_command(args, filelist):
                    logger.info(line)
                counter += 1
        else:
            logger.warning(f"Skipping {block} - already in HPSS")

    logger.info(f"{counter}/{len(block_launchers)} blocks backed up to HPSS.")
    return f"Done backing up {directory}."


# TODO cleanup command to double-check HPSS backup and remove source


@hpss.command()
@sbatch
@click.argument("inputfile", type=click.Path(exists=True))
@click.option(
    "-f",
    "patterns",
    multiple=True,
    show_default=True,
    default=[
        "INCAR*",
        "CONTCAR*",
        "KPOINTS*",
        "POSCAR*",
        "POTCAR*",
        "vasprun.xml*",
        "OUTCAR*",
    ],
    help="Set the pattern(s) to match files against in each launcher.",
)
def restore(inputfile, patterns):
    """Restore launchers from HPSS"""
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    nmax = ctx.parent.params["nmax"]
    directory = ctx.parent.params["directory"]

    if ctx.parent.params["pattern"]:
        raise EmmetCliError(f"--pattern not supported for HPSS restoral!")
    if not os.path.exists(directory):
        os.mkdirs(directory)

    shutil.chown(directory, group="matgen")
    block_launchers = defaultdict(list)
    with open(inputfile, "r") as infile:
        os.chdir(directory)
        with click.progressbar(infile, label="Load blocks") as bar:
            for line in bar:
                block, launcher = line.split(os.sep, 1)
                if len(block_launchers) == nmax and block not in block_launchers:
                    # already found nmax blocks. Order of launchers not guaranteed
                    continue
                for pattern in patterns:
                    block_launchers[block].append(
                        os.path.join(launcher.strip(), pattern)
                    )

    nblocks = len(block_launchers)
    nfiles = sum(len(v) for v in block_launchers.values())
    logger.info(f"Restore {nblocks} block(s) with {nfiles} patterns to {directory} ...")

    for block, files in block_launchers.items():
        # get full list of matching files in archive and check against existing files
        args = shlex.split(f"htar -tf garden/{block}.tar")
        filelist = [os.path.join(block, f) for f in files]
        filelist_restore, cnt = [], 0
        for line in run_command(args, filelist):
            ls = line.split()
            if len(ls) == 7:
                fn = ls[-1]
                cnt += 1
                if os.path.exists(fn):
                    logger.debug(f"Skipping {fn} - already exists on disk.")
                else:
                    filelist_restore.append(fn)

        # restore what's missing
        if filelist_restore:
            nfiles_restore = len(filelist_restore)
            if run:
                logger.info(
                    f"Restoring {nfiles_restore}/{cnt} files for {block} to {directory} ..."
                )
                args = shlex.split(f"htar -xvf garden/{block}.tar")
                run_command(args, filelist_restore)
            else:
                logger.info(
                    f"Would restore {nfiles_restore}/{cnt} files for {block} to {directory}."
                )
        else:
            logger.warning(f"Nothing to restore for {block}!")

        if run:
            logger.info(f"Setting group of {block} to matgen recursively ...")
            recursive_chown(block, "matgen")

    return f"Done restoring launchers from {inputfile}"
