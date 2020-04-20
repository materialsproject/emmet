import os
import shutil
import shlex
import logging
import click
import subprocess

from collections import defaultdict
from hpsspy import HpssOSError
from hpsspy.os.path import isfile
from emmet.cli.utils import get_vasp_dirs, EmmetCliError, ReturnCodes
from emmet.cli.decorators import sbatch


logger = logging.getLogger("emmet")
PREFIX = "block_"


@click.group()
@click.option(
    "-d", "--directory", required=True, help="Source or target directory for HPSS.",
)
@click.option(
    "-m", "--nmax", show_default=True, default=10, help="Maximum number of directories."
)
@click.option(
    "-p",
    "--pattern",
    show_default=True,
    default=f"{PREFIX}*",
    help="Pattern for sub-paths to include.",
)
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

    if counter is None:
        logger.error(f"No VASP calculations found in {directory}.")
        return ReturnCodes.ERROR

    logger.info(f"Prepared {counter+1} VASP calculation(s) in {directory}.")
    return ReturnCodes.SUCCESS


def run_command(args, filelist):
    # TODO deal with filelist too long
    nargs, nfiles, nshow = len(args), len(filelist), 1
    args += filelist
    args_short = (
        args[: nargs + nshow] + [f"({nfiles-1} more ...)"] if nfiles > nshow else args
    )
    logger.info(" ".join(args_short))
    popen = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
    )
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


def check_pattern():
    ctx = click.get_current_context()
    pattern = ctx.parent.params["pattern"]
    if os.sep in pattern:
        raise EmmetCliError(f"Nested pattern ({pattern}) not allowed!")
    elif not pattern.startswith(PREFIX):
        raise EmmetCliError(f"Pattern ({pattern}) only allowed to start with {PREFIX}!")


def load_block_launchers():
    ctx = click.get_current_context()
    nmax = ctx.parent.params["nmax"]
    block_launchers = defaultdict(list)
    for idx, vasp_dir in enumerate(get_vasp_dirs()):
        if idx and not idx % 500:
            logger.info(f"{idx} launchers found ...")
        launch_dir = PREFIX + vasp_dir.split(PREFIX, 1)[-1]
        block, launcher = launch_dir.split(os.sep, 1)
        if len(block_launchers) == nmax and block not in block_launchers:
            # already found nmax blocks. Order of launchers not guaranteed
            continue
        block_launchers[block].append(launcher)
    return block_launchers


def extract_filename(line):
    ls = line.strip().split()
    return ls[-1] if len(ls) == 7 else None


@hpss.command()
@sbatch
@click.option("--clean", is_flag=True, help="Remove original launchers.")
@click.option("--check", is_flag=True, help="Check backup consistency.")
def backup(clean, check):
    """Backup directory to HPSS"""
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    directory = ctx.parent.params["directory"]
    if not check and clean:
        logger.error("Not running --clean without --check enabled.")
        return ReturnCodes.ERROR

    check_pattern()

    logger.info("Discover launch directories ...")
    block_launchers = load_block_launchers()
    logger.info(f"Back up {len(block_launchers)} block(s) ...")

    counter, nremove_total = 0, 0
    os.chdir(directory)
    for block, launchers in block_launchers.items():
        logger.info(f"{block} with {len(launchers)} launcher(s)")
        try:
            isfile(f"garden/{block}.tar")
        except HpssOSError:  # block not in HPSS
            if run:
                filelist = [os.path.join(block, l) for l in launchers]
                args = shlex.split(f"htar -M 5000000 -Phcvf garden/{block}.tar")
                try:
                    for line in run_command(args, filelist):
                        logger.info(line.strip())
                except subprocess.CalledProcessError as e:
                    logger.error(str(e))
                    return ReturnCodes.ERROR
                counter += 1
        else:
            logger.warning(f"Skip {block} - already in HPSS")

        # Check backup here to allow running it separately
        if check:
            logger.info(f"Verify {block}.tar ...")
            args = shlex.split(
                f"htar -Kv -Hrelpaths -Hverify=all -f garden/{block}.tar"
            )
            files_remove = []
            try:
                for line in run_command(args, []):
                    line = line.strip()
                    if line.startswith("HTAR: V "):
                        ls = line.split(", ")
                        if len(ls) == 3:
                            nfiles = len(files_remove)
                            if nfiles and not nfiles % 1000:
                                logger.info(f"{nfiles} files ...")
                            files_remove.append(ls[0].split()[-1])
                    else:
                        logger.info(line)
            except subprocess.CalledProcessError as e:
                logger.error(str(e))
                return ReturnCodes.ERROR

            if clean:
                nremove = len(files_remove)
                nremove_total += nremove
                if run:
                    with click.progressbar(files_remove, label="Removing files") as bar:
                        for fn in bar:
                            os.remove(fn)
                    logger.info(f"Removed {nremove} files from disk for {block}.")
                else:
                    logger.info(f"Would remove {nremove} files from disk for {block}.")

    logger.info(f"{counter}/{len(block_launchers)} blocks newly backed up to HPSS.")
    if clean:
        if run:
            logger.info(f"Verified and removed a total of {nremove_total} files.")
        else:
            logger.info(f"Would verify and remove a total of {nremove_total} files.")
    return ReturnCodes.SUCCESS


@hpss.command()
@sbatch
@click.option(
    "-l",
    "--inputfile",
    required=True,
    type=click.Path(exists=True),
    help="Text file with list of launchers to restore (relative to `directory`).",
)
@click.option(
    "-f",
    "--file-filter",
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
    help="Set the file filter(s) to match files against in each launcher.",
)
def restore(inputfile, file_filter):
    """Restore launchers from HPSS"""
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    nmax = ctx.parent.params["nmax"]
    directory = ctx.parent.params["directory"]

    if ctx.parent.params["pattern"] != f"{PREFIX}*":
        # TODO respect both pattern and inputfile for restoral
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
                for ff in file_filter:
                    block_launchers[block].append(os.path.join(launcher.strip(), ff))

    nblocks = len(block_launchers)
    nfiles = sum(len(v) for v in block_launchers.values())
    logger.info(
        f"Restore {nblocks} block(s) with {nfiles} file filters to {directory} ..."
    )

    nfiles_restore_total = 0
    for block, files in block_launchers.items():
        # get full list of matching files in archive and check against existing files
        args = shlex.split(f"htar -tf garden/{block}.tar")
        filelist = [os.path.join(block, f) for f in files]
        filelist_restore, cnt = [], 0
        try:
            for line in run_command(args, filelist):
                fn = extract_filename(line)
                if fn:
                    cnt += 1
                    if os.path.exists(fn):
                        logger.debug(f"Skip {fn} - already exists on disk.")
                    else:
                        filelist_restore.append(fn)
        except subprocess.CalledProcessError as e:
            logger.error(str(e))
            return ReturnCodes.ERROR

        # restore what's missing
        if filelist_restore:
            nfiles_restore = len(filelist_restore)
            nfiles_restore_total += nfiles_restore
            if run:
                logger.info(
                    f"Restore {nfiles_restore}/{cnt} files for {block} to {directory} ..."
                )
                args = shlex.split(f"htar -xvf garden/{block}.tar")
                try:
                    for line in run_command(args, filelist_restore):
                        logger.info(line.strip())
                except subprocess.CalledProcessError as e:
                    logger.error(str(e))
                    return ReturnCodes.ERROR
            else:
                logger.info(
                    f"Would restore {nfiles_restore}/{cnt} files for {block} to {directory}."
                )
        else:
            logger.warning(f"Nothing to restore for {block}!")

        if run:
            logger.info(f"Set group of {block} to matgen recursively ...")
            recursive_chown(block, "matgen")

    if run:
        logger.info(f"Restored {nfiles_restore_total} files to {directory}.")
    else:
        logger.info(f"Would restore {nfiles_restore_total} files to {directory}.")
    return ReturnCodes.SUCCESS
