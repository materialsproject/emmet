import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

import click
from hpsspy import HpssOSError
from hpsspy.os.path import isfile

from emmet.cli.legacy import SETTINGS
from emmet.cli.legacy.decorators import sbatch
from emmet.cli.legacy.parse_driver import (
    ParseDriverError,
    discover_launchers,
    make_client,
    plan_parse,
    run_parse,
)
from emmet.cli.legacy.utils import (
    EmmetCliError,
    ReturnCodes,
    VaspDirsGenerator,
    get_symlinked_path,
    reorganize_blocks,
)
from emmet.core.vasp.models import VOLUMETRIC_PARSERS
from emmet.core.vasp.parse import ParsePolicy
from emmet.core.vasp.parsed import ParseOutcome
from emmet.core.vasp.utils import DEFAULT_CALC_SUFFIXES

logger = logging.getLogger("emmet")
GARDEN = "/home/m/matcomp/garden"
PREFIXES = ["res_", "aflow_", "block_"]
FILE_FILTERS = [
    "INCAR*",
    "CONTCAR*",
    "KPOINTS*",
    "POSCAR*",
    "POTCAR*",
    "OUTCAR*",
    "vasprun.xml*",
    "transformation*",
]

STORE_VOLUMETRIC_DATA = ["CHGCAR", "LOCPOT", "AECCAR0", "AECCAR1", "AECCAR2", "ELFCAR"]

for v in STORE_VOLUMETRIC_DATA:
    FILE_FILTERS.append(f"{v}*")

FILE_FILTERS_DEFAULT = [
    f"{d}{os.sep}{f}" if d else f
    for f in FILE_FILTERS
    for d in ["", "relax1", "relax2"]
]


@click.group()
@click.option(
    "-d",
    "--directory",
    required=True,
    help="Working directory to use for HPSS or parsing.",
)
@click.option(
    "-m", "--nmax", show_default=True, default=10, help="Maximum number of directories."
)
@click.option(
    "-p",
    "--pattern",
    show_default=True,
    default="block_*",
    help="Pattern for sub-paths to include.",
)
def tasks(directory, nmax, pattern):
    """Backup, restore, and parse VASP calculations."""
    pass


def make_comment(ctx, txt):
    gh = ctx.grand_parent.obj["GH"]
    user = gh.me().login
    issue_number = ctx.grand_parent.params["issue"]
    issue = gh.issue(SETTINGS.tracker["org"], SETTINGS.tracker["repo"], issue_number)
    comment = issue.create_comment("\n".join(txt))
    logger.info(comment.html_url)


@tasks.command()
@sbatch
@click.option("--clean", is_flag=True, help="Remove original launchers.")
@click.option(
    "--exhaustive",
    is_flag=True,
    help="Check backup consistency for each block/launcher individually",
)
@click.option("--tar", is_flag=True, help="tar blocks after backup and clean")
@click.pass_context
def backups(ctx, clean, exhaustive, tar):
    """Scan root directory and submit separate backup jobs for subdirectories containing blocks"""
    ctx.parent.params["nmax"] = sys.maxsize  # disable maximum launchers for backup
    subdir_block_launchers = defaultdict(lambda: defaultdict(list))
    gen = VaspDirsGenerator()

    for vasp_dir in gen:
        subdir, block, launcher = split_vasp_dir_path(vasp_dir)
        subdir_block_launchers[subdir][block].append(launcher)

    if not gen.value:
        logger.warning("No launchers found.")
        return ReturnCodes.SUCCESS

    logger.info(f"Found {gen.value} launchers.")
    rootdir = ctx.parent.params["directory"]
    rootdir_pattern = os.path.join(rootdir, ctx.parent.params["pattern"])
    comment_txt = [f"Backup {gen.value} launchers in `{rootdir_pattern}`:\n"]
    ctx.parent.parent.params["sbatch"] = True
    run = ctx.parent.parent.params["run"]
    prefix = ctx.parent.params["pattern"] = "block_*"

    for subdir, block_launchers in subdir_block_launchers.items():
        nblocks = len(block_launchers)
        nlaunchers = sum(len(v) for v in block_launchers.values())
        subdir_short = subdir.replace(rootdir, "")
        # TODO further split up jobs by prefix if `block_*` is too many
        msg = f"- `{subdir_short}{prefix}` ({nblocks}/{nlaunchers})"

        if run:
            ctx.parent.params["directory"] = subdir
            ret = ctx.parent.invoke(backup, clean=clean, check=True, tar=tar)
            msg += f" -> {ret.value}"
            comment_txt.append(msg)
        else:
            logger.info(msg)

    if run:
        make_comment(ctx, comment_txt)

    return ReturnCodes.SUCCESS


def run_command(args, filelist):
    nargs, nfiles, nshow = len(args), len(filelist), 1
    full_args = args + filelist
    args_short = (
        full_args[: nargs + nshow] + [f"({nfiles - 1} more ...)"]
        if nfiles > nshow
        else full_args
    )
    logger.info(" ".join(args_short))
    popen = subprocess.Popen(
        full_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    for stdout_line in iter(popen.stdout.readline, ""):
        yield stdout_line
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, full_args)


def recursive_chown(path, group):
    for dirpath, dirnames, filenames in os.walk(path):
        if Path(dirpath).group() != group:
            shutil.chown(dirpath, group=group)
        for filename in filenames:
            fullpath = os.path.join(dirpath, filename)
            if Path(fullpath).group() != group:
                shutil.chown(fullpath, group=group)


def check_pattern(nested_allowed=False):
    ctx = click.get_current_context()
    pattern = ctx.parent.params["pattern"]
    if not nested_allowed and os.sep in pattern:
        raise EmmetCliError(f"Nested pattern ({pattern}) not allowed!")
    elif not any(pattern.startswith(p) for p in PREFIXES):
        raise EmmetCliError(
            f"Pattern ({pattern}) only allowed to start with one of {PREFIXES}!"
        )


def split_vasp_dir_path(vasp_dir):
    prefix = "block_"  # TODO should use PREFIXES?
    if prefix not in vasp_dir:
        ctx = click.get_current_context()
        offset = len(ctx.parent.params["pattern"].split(os.sep))
        base_path = ctx.parent.params["directory"].rstrip(os.sep)
        base_path_index = len(base_path.split(os.sep)) + offset
        vasp_dir = get_symlinked_path(vasp_dir, base_path_index)

    vasp_dir_split = vasp_dir.split(prefix, 1)
    vasp_dir_split_len = len(vasp_dir_split)
    if vasp_dir_split_len == 2:
        launch_dir = prefix + vasp_dir_split[-1]
        block, launcher = launch_dir.split(os.sep, 1)
        return vasp_dir_split[0], block, launcher
    else:
        raise EmmetCliError(f"Failed to split vasp dir {vasp_dir}!")


def load_block_launchers():
    # NOTE this runs within subdir (i.e. block_* directories at root of subdir)
    block_launchers = defaultdict(list)
    gen = VaspDirsGenerator()
    for vasp_dir in gen:
        _, block, launcher = split_vasp_dir_path(vasp_dir)
        block_launchers[block].append(launcher)
    logger.info(f"Loaded {len(block_launchers)} block(s) with {gen.value} launchers.")
    return block_launchers


def extract_filename(line):
    ls = line.strip().split()
    return ls[-1] if len(ls) == 7 else None


@tasks.command()
@sbatch
@click.option("--reorg", is_flag=True, help="Reorganize directory in block/launchers.")
@click.option("--clean", is_flag=True, help="Remove original launchers.")
@click.option("--check", is_flag=True, help="Check backup consistency.")
@click.option(
    "--exhaustive",
    is_flag=True,
    help="Check backup consistency for each block/launcher individually",
)
@click.option("--force-new", is_flag=True, help="Generate new backup.")
@click.option("--tar", is_flag=True, help="tar blocks after backup and clean")
@click.option(
    "--max-launchers",
    type=int,
    default=50,
    show_default=True,
    help="Max launchers per block when using --reorg.",
)
@click.pass_context
def backup(ctx, reorg, clean, check, exhaustive, force_new, tar, max_launchers):
    """Backup directory to HPSS"""
    run = ctx.parent.parent.params["run"]
    ctx.params["nmax"] = sys.maxsize
    logger.warning("--nmax ignored for HPSS backup!")
    directory = ctx.parent.params["directory"]
    if not check and clean:
        logger.error("Not running --clean without --check enabled.")
        return ReturnCodes.ERROR

    if not clean and tar:
        logger.error("Not running --tar without --clean enabled.")
        return ReturnCodes.ERROR

    if not reorg:
        check_pattern()

    logger.info("Discover launch directories ...")
    block_launchers = load_block_launchers()

    if reorg:
        block_launchers = reorganize_blocks(
            block_launchers, directory, max_per_block=max_launchers
        )
        logger.info(
            f"After reorganization: {len(block_launchers)} block(s) "
            f"with max {max_launchers} launchers each."
        )

    counter, nremove_total = 0, 0
    os.chdir(directory)
    for block, launchers in block_launchers.items():
        nlaunchers = len(launchers)
        logger.info(f"{block} with {nlaunchers} launcher(s)")
        filelist = [os.path.join(block, l) for l in launchers]

        try:
            isfile(f"{GARDEN}/{block}.tar")
            if force_new and run:
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                tarfile = f"{GARDEN}/{block}.tar"
                for suf in ["", ".idx"]:
                    args = shlex.split(
                        f"hsi -q mv -v {tarfile}{suf} {tarfile}{suf}.bkp_{ts}"
                    )
                    for line in run_command(args, []):
                        logger.info(line.strip())
                raise HpssOSError
        except HpssOSError:  # block not in HPSS
            if run:
                directory = ctx.parent.params["directory"]
                track_dir = os.path.join(directory, ".emmet")
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                filename = os.path.join(track_dir, f"{block}_launchers_{ts}.txt")

                with open(filename, "w") as f:
                    for line in filelist:
                        f.write(f"{line}\n")

                args = shlex.split(
                    f"htar -M 5000000 -Phcf {GARDEN}/{block}.tar -L {filename}"
                )
                try:
                    for line in run_command(args, []):
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
                f"htar -K -Hrelpaths -Hverify=all -f {GARDEN}/{block}.tar"
            )

            failed_verification = []

            if exhaustive:
                for launcher in launchers:
                    try:
                        for line in run_command(args, [f"{block}/{launcher}"]):
                            logger.info(line.strip())
                    except subprocess.CalledProcessError as e:
                        logger.error(str(e))
                        click.secho(
                            f"Failed to verify {block}/{launcher}",
                            fg="red",
                        )
                        failed_verification.append(f"{block}/{launcher}")
                        continue
            else:
                try:
                    for line in run_command(args, []):
                        logger.info(line.strip())
                except subprocess.CalledProcessError as e:
                    logger.error(str(e))
                    return ReturnCodes.ERROR

        if clean:
            safe_to_remove = [f for f in filelist if f not in failed_verification]
            nremove_block = len(safe_to_remove)
            n_skip = len(failed_verification)
            nremove_total += nremove_block

            if run:
                with click.progressbar(
                    safe_to_remove, label=f"removing {nremove_block} launchers..."
                ) as bar:
                    for fn in bar:
                        if os.path.exists(fn):
                            shutil.rmtree(fn)
                logger.info(
                    f"Verified and removed a total of {nremove_block} launchers from disk for {block},"
                    f"skipped {n_skip} launchers that failed HPSS verification."
                )

                if tar:
                    args = shlex.split(f"tar czf {block}.tar.gz --remove-files {block}")
                    try:
                        for line in run_command(args, []):
                            logger.info(line.strip())
                    except subprocess.calledprocesserror as e:
                        logger.error(str(e))
                        return ReturnCodes.ERROR

                    logger.info(f"Successfully compressed {block} to {block}.tar.gz")

            else:
                logger.info(
                    f"Would verify and remove a total of {nremove_block} launchers for {block} and skip {n_skip}"
                    f"launchers that failed HPSS verfication."
                )

                if tar:
                    logger.info(f"Would compress {block} to {block}.tar.gz")

    logger.info(f"{counter}/{len(block_launchers)} blocks newly backed up to HPSS.")

    if clean:
        if run:
            logger.info(f"Verified and removed a total of {nremove_total} launchers.")
        else:
            logger.info(
                f"Would verify and remove a total of {nremove_total} launchers."
            )
    return ReturnCodes.SUCCESS


@tasks.command()
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
    default=FILE_FILTERS_DEFAULT,
    help="Set the file filter(s) to match files against in each launcher.",
)
def restore(inputfile, file_filter):  # noqa: C901
    """Restore launchers from HPSS"""
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    nmax = ctx.parent.params["nmax"]
    pattern = ctx.parent.params["pattern"]
    directory = ctx.parent.params["directory"]
    if not os.path.exists(directory):
        os.makedirs(directory)

    check_pattern(nested_allowed=True)
    if Path(directory).group() != "matgen":
        shutil.chown(directory, group="matgen")

    block_launchers = defaultdict(list)
    nlaunchers = 0
    with open(inputfile, "r") as infile:
        os.chdir(directory)
        with click.progressbar(infile, label="Load blocks") as bar:
            for line in bar:
                if fnmatch(line, pattern):
                    if nlaunchers == nmax:
                        break
                    if os.sep in line:
                        block, launcher = line.split(os.sep, 1)
                    else:
                        block, launcher = line.strip(), ""
                    for ff in file_filter:
                        block_launchers[block].append(
                            os.path.join(launcher.strip(), ff)
                        )
                    # also try restoring unnested block_/launcher_ (result of --reorg flag)
                    if os.sep in launcher:
                        launcher = launcher.strip().split(os.sep)[-1]
                        for ff in file_filter:
                            block_launchers[block].append(
                                os.path.join(launcher.strip(), ff)
                            )
                    nlaunchers += 1

    nblocks = len(block_launchers)
    nfiles = sum(len(v) for v in block_launchers.values())
    logger.info(
        f"Restore {nblocks} block(s) with {nlaunchers} launchers"
        f" and {nfiles} file filters to {directory} ..."
    )

    nfiles_restore_total, max_args = 0, 14000
    for block, files in block_launchers.items():
        # check if block exists in HPSS
        try:
            isfile(f"{GARDEN}/{block}.tar")
        except HpssOSError:
            logger.error(f"{block} does not exist in HPSS!")
            continue

        # get full list of matching files in archive and check against existing files
        args = shlex.split(f"htar -tf {GARDEN}/{block}.tar")
        filelist = [os.path.join(block, f) for f in files]
        filelist_chunks = [
            filelist[i : i + max_args] for i in range(0, len(filelist), max_args)
        ]
        filelist_restore, cnt = [], 0
        try:
            for chunk in filelist_chunks:
                for line in run_command(args, chunk):
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
                args = shlex.split(f"htar -xf {GARDEN}/{block}.tar")
                filelist_restore_chunks = [
                    filelist_restore[i : i + max_args]
                    for i in range(0, len(filelist_restore), max_args)
                ]
                try:
                    for chunk in filelist_restore_chunks:
                        for line in run_command(args, chunk):
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


def group_strings_by_prefix(strings, prefix_length):
    """group a list of strings by prefix based on a given prefix length"""
    groups = defaultdict(list)
    for s in strings:
        prefix = s[:prefix_length]
        groups[prefix].append(s)

    return groups


@tasks.command()
@sbatch
@click.option(  # NOTE this could be retrieved from S3 in the future
    "--task-ids",
    type=click.Path(exists=True),
    help="JSON file mapping launcher name to task ID.",
)
@click.pass_context
def parsers(ctx, task_ids):
    """Scan root directory and submit separate parser jobs (DISABLED)"""
    raise EmmetCliError(
        "parsers is disabled: parse now gives identifiers which continue from the "
        "highest one already used, so several parse jobs started at once would give "
        "the same identifiers to different calculations. Run `tasks parse` for one "
        "directory at a time until the identifiers of the jobs can be split."
    )
    ctx.parent.params["nmax"] = (
        sys.maxsize
    )  # disable maximum launchers to determine parser jobs
    run = ctx.parent.parent.params["run"]
    directory = ctx.parent.params["directory"]
    check_pattern()
    gen = VaspDirsGenerator()
    launchers = []

    for vaspdir in gen:
        _, block, launcher = split_vasp_dir_path(vaspdir)
        launchers.append(os.path.join(block, launcher))

    pattern = ctx.parent.params["pattern"]
    nparse_max, len_prefix = 5000, len(pattern[:-1])  # NOTE assuming endswith *
    remaining = group_strings_by_prefix(launchers, len_prefix)
    logger.info(f"Loaded {gen.value} launchers.")
    patterns = {}

    while remaining:
        for prefix in list(remaining.keys()):
            nlaunchers = len(remaining[prefix])
            if nlaunchers <= nparse_max:
                patterns[f"{prefix}*"] = nlaunchers
                remaining.pop(prefix)

        len_prefix += 1
        remaining_vaspdirs = [x for v in remaining.values() for x in v]
        remaining = group_strings_by_prefix(remaining_vaspdirs, len_prefix)

    ctx.parent.parent.params["sbatch"] = True
    rootdir_pattern = os.path.join(directory, ctx.parent.params["pattern"])
    comment_txt = [f"Parse {gen.value} launchers in `{rootdir_pattern}`:\n"]

    for pattern, nlaunchers in patterns.items():
        msg = f"- `{pattern}` ({nlaunchers})"
        if run:
            ctx.parent.params["pattern"] = pattern
            ctx.parent.params["nmax"] = nlaunchers
            ret = ctx.parent.invoke(parse, task_ids=task_ids)
            msg += f" -> {ret.value}"
            comment_txt.append(msg)
            time.sleep(90)  # give jobs time to start (cf insertion of separator task)
        else:
            logger.info(msg)

    if run:
        make_comment(ctx, comment_txt)

    return ReturnCodes.SUCCESS


def _parse_options(func):
    """The options of the parse command."""
    options = [
        click.option(
            "--output-dir",
            type=click.Path(file_okay=False),
            help="Directory for the Parquet tables. Required with --run. Identifiers "
            "continue from those already in its tasks table.",
        ),
        click.option(
            "--task-ids",
            type=click.Path(exists=True),
            help="JSON file mapping launcher/calc_suffix to task ID, e.g., "
            '"launcher_2020-03-11/relax1". A launcher with a single calculation '
            "can be given without the suffix.",
        ),
        click.option(
            "--delta-tasks-uri",
            help="Delta table of tasks whose identifiers are not to be used again, "
            "e.g., s3://bucket/core/tasks/. Needs deltalake.",
        ),
        click.option(
            "--delta-option",
            "delta_options",
            multiple=True,
            metavar="KEY=VALUE",
            help="Storage option to read the Delta table with, e.g., "
            "AWS_REGION=us-east-1. Can be repeated.",
        ),
        click.option(
            "--scheduler-address", help="Address of a running Dask scheduler."
        ),
        click.option(
            "--scheduler-file",
            help="File a running Dask scheduler wrote its address to.",
        ),
        click.option(
            "--nworkers",
            type=int,
            help="Number of workers of the Dask cluster started on this machine, "
            "if there is no scheduler.",
        ),
        click.option(
            "--chunk-size",
            type=int,
            default=20,
            show_default=True,
            help="Number of calculations a worker parses at a time.",
        ),
        click.option(
            "-s",
            "--store-volumetric-data",
            multiple=True,
            help="Store only these volumetric files, e.g., CHGCAR or LOCPOT: any of "
            f"{', '.join(VOLUMETRIC_PARSERS)}. All of them by default.",
        ),
        click.option(
            "-r",
            "--runs",
            multiple=True,
            default=DEFAULT_CALC_SUFFIXES,
            show_default=True,
            help="Suffixes of the calculations in a directory, in the order they "
            "were run. Subfolders with these names are also searched.",
        ),
        click.option(
            "--no-dos", is_flag=True, help="Do not store densities of states."
        ),
        click.option(
            "--no-bandstructure", is_flag=True, help="Do not store band structures."
        ),
        click.option(
            "--no-projections",
            is_flag=True,
            help="Do not store the projections of densities of states and band structures.",
        ),
        click.option(
            "--include-failed",
            is_flag=True,
            help="Also store the large objects of calculations VASP did not complete.",
        ),
        click.option(
            "--batch-id",
            help="Batch identifier of the tasks. Default is the name of the directory.",
        ),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _make_policy(
    store_volumetric_data, no_dos, no_bandstructure, no_projections, include_failed
) -> ParsePolicy:
    config = {
        "volumetric_types": tuple(store_volumetric_data) or None,
        "dos_projections": not no_projections,
        "bandstructure_projections": not no_projections,
        "include_failed": include_failed,
    }
    if no_dos:
        config["dos_task_types"] = ()
    if no_bandstructure:
        config["bandstructure_task_types"] = ()
    try:
        return ParsePolicy(**config)
    except ValueError as exc:
        raise EmmetCliError(str(exc)) from exc


@tasks.command()
@sbatch
@_parse_options
def parse(  # noqa: C901
    output_dir,
    task_ids,
    delta_tasks_uri,
    delta_options,
    scheduler_address,
    scheduler_file,
    nworkers,
    chunk_size,
    store_volumetric_data,
    runs,
    no_dos,
    no_bandstructure,
    no_projections,
    include_failed,
    batch_id,
):
    """Parse VASP launchers into Parquet tables (EXPERIMENTAL).

    Every calculation of a launcher is a row of the tasks table, and its
    trajectory, density of states, band structure and volumetric data are rows of
    their own tables. The launchers are not changed.

    Without --run the launchers are only searched, and the calculations and the
    identifiers they would be given are reported.
    """
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    nmax = ctx.parent.params["nmax"]
    pattern = ctx.parent.params["pattern"]
    directory = ctx.parent.params["directory"].rstrip(os.sep)
    tag = os.path.basename(directory)
    batch_id = batch_id or tag

    if invalid := {c for c in batch_id if not (c.isalnum() or c in "-_")}:
        raise EmmetCliError(
            f"Invalid characters in the batch id {batch_id!r}: {' '.join(sorted(invalid))}. "
            "Use --batch-id."
        )
    if run and not output_dir:
        raise EmmetCliError("Need --output-dir to write the parsed tables!")

    storage_options = {}
    for option in delta_options:
        key, sep, value = option.partition("=")
        if not sep:
            raise EmmetCliError(
                f"Expected KEY=VALUE for --delta-option, got {option!r}."
            )
        storage_options[key] = value

    policy = _make_policy(
        store_volumetric_data, no_dos, no_bandstructure, no_projections, include_failed
    )
    identifiers = None
    if task_ids:
        with open(task_ids) as f:
            identifiers = json.load(f)

    try:
        plan = plan_parse(
            discover_launchers(directory, pattern, nmax),
            suffixes=tuple(runs),
            output_dir=output_dir,
            delta_uri=delta_tasks_uri,
            delta_storage_options=storage_options,
            task_ids=identifiers,
        )
    except ParseDriverError as exc:
        raise EmmetCliError(str(exc)) from exc

    for line in plan.report():
        logger.info(line)

    if not run:
        logger.info(
            f"Would parse {plan.calculations} calculation(s) in {directory}. "
            "Nothing was written."
        )
        return ReturnCodes.SUCCESS if plan.calculations else ReturnCodes.WARNING

    if not plan.calculations:
        logger.warning("No calculations to parse.")
        return ReturnCodes.WARNING

    try:
        client = make_client(scheduler_address, scheduler_file, nworkers)
    except Exception as exc:
        raise EmmetCliError(f"Could not start or connect to Dask: {exc}") from exc
    try:
        result = run_parse(
            plan.items,
            output_dir,
            policy,
            client=client,
            chunk_size=chunk_size,
            batch_id=batch_id,
            tags=[tag, SETTINGS.year_tags[-1]],
            suffixes=tuple(runs),
        )
    finally:
        cluster = getattr(client, "cluster", None)
        client.close()
        if cluster is not None and not (scheduler_address or scheduler_file):
            cluster.close()

    for line in result.summary():
        logger.info(line)
    parsed = sum(m.outcome == ParseOutcome.PARSED for m in result.manifests)
    if parsed and not result.failed_chunks:
        return ReturnCodes.SUCCESS
    return ReturnCodes.WARNING


@tasks.command()
@sbatch
@click.pass_context
def survey(ctx):
    """
    Recursively search root directory for blocks containing VASP files.
    Requires GNU Parallel to be installed and on path.
    """

    if not shutil.which("parallel"):
        logger.error(
            """
              Survey requires GNU Parallel, if you are on NERSC run 'module load parallel' and retry.
              Consider adding 'module load parallel' to your .bashrc to avoid this error in the future.

              For use outside of NERSC, GNU Parallel can be installed from the Free Software Foundation
              at gnu.org/software/parallel/
           """
        )
        return ReturnCodes.ERROR

    run = ctx.parent.parent.params["run"]
    root_dir = ctx.parent.params["directory"]

    if run:
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        args = shlex.split(
            f"launcher_finder -d {root_dir} -f emmet-launcher-report-{ts}.txt"
        )
        for line in run_command(args, []):
            logger.info(line.strip())

        logger.info(f"launcher search results stored in {root_dir}/.emmet/")
    else:
        logger.info(
            f"Would recursively search for directories containing VASP files in {root_dir}"
        )
        logger.info(
            f"Run 'launcher_finder {root_dir}' if you want to search without GH issue tracking"
        )

    return ReturnCodes.SUCCESS
