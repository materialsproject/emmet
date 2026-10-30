import itertools
import logging
import os
import shutil
import stat
from collections import defaultdict
from enum import Enum
from fnmatch import fnmatch
from glob import glob
from pathlib import Path

import click
import mgzip
from fireworks.fw_config import FW_BLOCK_FORMAT
from pymatgen.core import Structure

from emmet.cli.legacy import SETTINGS
from emmet.cli.legacy.db import StorageGateway  # noqa: F401  (used by other modules)
from emmet.core.utils import group_structures, utcnow

logger = logging.getLogger("emmet")
perms = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP


class EmmetCliError(Exception):
    pass


class ReturnCodes(Enum):
    """codes to print command exit message in github issue comments"""

    SUCCESS = "COMPLETED"
    ERROR = "encountered ERROR"
    WARNING = "exited with WARNING"


def structures_match(s1, s2):
    return bool(len(list(group_structures([s1, s2]))) == 1)


def ensure_indexes(indexes, colls):
    created = defaultdict(list)
    for index in indexes:
        for coll in colls:
            keys = [k.rsplit("_", 1)[0] for k in coll.index_information().keys()]
            if index not in keys:
                coll.create_index(index)
                created[coll.full_name].append(index)

    if created:
        indexes = ", ".join(created[coll.full_name])
        logger.debug(f"Created the following index(es) on {coll.full_name}:\n{indexes}")


def get_meta_from_structure(struct):
    d = {"formula_pretty": struct.composition.reduced_formula}
    d["nelements"] = len(set(struct.composition.elements))
    d["nsites"] = len(struct)
    d["is_ordered"] = struct.is_ordered
    d["is_valid"] = struct.is_valid()
    return d


def aggregate_by_formula(coll, q, key=None):
    query = {"$and": [q, SETTINGS.exclude]}
    query.update(SETTINGS.base_query)
    nested = False
    if key is None:
        for k in SETTINGS.aggregation_keys:
            q = {k: {"$exists": 1}}
            q.update(SETTINGS.base_query)
            doc = coll.find_one(q)
            if doc:
                key = k
                nested = int("snl" in doc)
                break
        else:
            raise ValueError(
                f"could not find one of the aggregation keys {SETTINGS.aggregation_keys} in {coll.full_name}!"
            )

    push = {k.split(".")[-1]: f"${k}" for k in SETTINGS.structure_keys[bool(nested)]}
    return coll.aggregate(
        [
            {"$match": query},
            {"$sort": {"nelements": 1, "nsites": 1}},
            {"$group": {"_id": f"${key}", "structures": {"$push": push}}},
        ],
        allowDiskUse=True,
        batchSize=1,
    )


def load_structure(dct):
    s = Structure.from_dict(dct)
    s.remove_oxidation_states()
    return s.get_primitive_structure()


# a utility function to get us a slice of an iterator, as an iterator
# when working with iterators maximum lazyness is preferred
def iterator_slice(iterator, length):
    iterator = iter(iterator)
    while True:
        res = tuple(itertools.islice(iterator, length))
        if not res:
            break
        yield res


def chunks(lst, n):
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def get_subdir(dn):
    return dn.rstrip(os.sep).rsplit(os.sep, 1)[-1]


def get_timestamp_dir(prefix="launcher"):
    time_now = utcnow().strftime(FW_BLOCK_FORMAT)
    return "_".join([prefix, time_now])


def get_dir_type(list_of_files):
    for f in list_of_files:
        if f.startswith("INCAR"):
            return "vasp"
        elif f.startswith("feff.inp"):
            return "feff"
        elif f.startswith("mol.qin."):
            return "mol"
    else:
        return None


def make_block(base_path):
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    block = get_timestamp_dir(prefix="block")
    block_dir = os.path.join(base_path, block)
    if run:
        os.mkdir(block_dir)
    return block_dir


def get_symlinked_path(root, base_path_index):
    """organize directory in block_*/launcher_*"""
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    root_split = root.split(os.sep)
    base_path = os.sep.join(root_split[:base_path_index])

    if root_split[base_path_index].startswith("block_"):
        block_dir = os.sep.join(root_split[: base_path_index + 1])
    else:
        all_blocks = glob(os.path.join(base_path, "block_*/"))
        for block_dir in all_blocks:
            p = os.path.join(block_dir, "launcher_*/")
            if len(glob(p)) < 500:
                break
        else:
            # didn't find a block with < 500 launchers
            block_dir = make_block(base_path)

    if root_split[-1].startswith("launcher_"):
        launch_dir = os.path.join(block_dir, root_split[-1])
        if not os.path.exists(launch_dir):
            if run:
                rename_dir(root, launch_dir)
            logger.debug(f"{root} -> {launch_dir}")
    else:
        launch = get_timestamp_dir(prefix="launcher")
        launch_dir = os.path.join(block_dir, launch)
        if run:
            rename_dir(root, launch_dir)
        logger.debug(f"{root} -> {launch_dir}")

    return launch_dir


def rename_dir(root, launch_dir):
    fn = "ORIG_PATH"
    with Path(os.sep.join([root, fn])).open("w") as f:
        f.write(root)

    os.rename(root, launch_dir)


# https://stackoverflow.com/a/34073559
class VaspDirsGenerator:
    def __init__(self):
        self.gen = get_vasp_dirs()

    def __iter__(self):
        self.value = yield from self.gen


def get_vasp_dirs():
    ctx = click.get_current_context()
    nmax = ctx.parent.params["nmax"]
    pattern = ctx.parent.params["pattern"]
    run = ctx.parent.parent.params["run"] and pattern.startswith("block_")
    reorg = ctx.params.get("reorg")

    base_path = ctx.parent.params["directory"].rstrip(os.sep)
    base_path_index = len(base_path.split(os.sep))
    if pattern:
        pattern_split = pattern.split(os.sep)
        pattern_split_len = len(pattern_split)

    counter = 0
    for root, dirs, files in os.walk(base_path, topdown=True):
        if counter and not counter % 2000:
            logger.info(f"{counter} launchers found ...")
        if counter == nmax:
            break

        level = len(root.split(os.sep)) - base_path_index
        if pattern and dirs and pattern_split_len > level:
            p = pattern_split[level]
            dirs[:] = [d for d in dirs if fnmatch(d, p)]

        for d in dirs:
            dn = os.path.join(root, d)
            st = os.stat(dn)
            if not bool(st.st_mode & perms):
                raise EmmetCliError(f"Insufficient permissions {st.st_mode} for {dn}.")

        dir_type = get_dir_type(files)

        if dir_type:
            gzipped = False
            for f in files:
                fn = os.path.join(root, f)
                if os.path.islink(fn):
                    if run:
                        fn_real = os.path.realpath(fn)
                        if os.path.exists(fn_real):
                            dst_name = f"{f}_copy"
                            dst = os.path.join(root, dst_name)
                            if os.path.isdir(fn_real):
                                shutil.copytree(fn_real, dst)
                            else:
                                shutil.copy(fn_real, dst)

                            os.unlink(fn)
                            shutil.move(dst, fn)
                            logger.debug(f"Resolved {fn}.")
                        else:
                            os.unlink(fn)
                            logger.debug(f"Unlinked {fn}.")
                    else:
                        logger.debug(f"Would resolve or unlink {fn}.")
                    continue

                st = os.stat(fn)
                if not bool(st.st_mode & perms):
                    raise EmmetCliError(
                        f"Insufficient permissions {st.st_mode} for {fn}."
                    )

                if run and not f.endswith(".gz"):
                    fn_gz = fn + ".gz"
                    if os.path.exists(fn_gz):
                        os.remove(fn_gz)  # remove left-over gz (cancelled job)

                    with open(fn, "rb") as fo, mgzip.open(fn_gz, "wb", thread=0) as fw:
                        fw.write(fo.read())

                    if os.path.exists(fn):
                        os.remove(fn)  # remove original

                    shutil.chown(fn_gz, group="matgen")
                    gzipped = True

            # NOTE skip symlink'ing on MP calculations from the early days
            vasp_dir = get_symlinked_path(root, base_path_index) if reorg else root

            dirs[:] = []  # don't descend further (i.e. ignore relax1/2)
            logger.log(logging.INFO if gzipped else logging.DEBUG, vasp_dir)
            yield vasp_dir
            counter += 1

    return counter


def reconstruct_command(sbatch=False):
    ctx = click.get_current_context()
    command = []
    for level, (cmd, params) in enumerate(
        zip(
            ctx.command_path.split(),
            [ctx.grand_parent.params, ctx.parent.params, ctx.params],
        )
    ):
        command.append(cmd)
        if level:
            command.append("\\\n")
        for k, v in params.items():
            k = k.replace("_", "-")
            if v:
                if isinstance(v, bool):
                    if (sbatch and k != "sbatch" and k != "bb") or not sbatch:
                        command.append(f"--{k}")
                elif isinstance(v, str):
                    command.append(f'--{k}="{v}"')
                elif isinstance(v, tuple) or isinstance(v, list):
                    for x in v:
                        command.append(f'--{k}="{x}"')
                        command.append("\\\n")
                else:
                    command.append(f"--{k}={v}")
                if level:
                    command.append("\\\n")

    return " ".join(command).strip().strip("\\")


def find_leaf_launchers(block_path):
    """
    Walk a block directory and find all leaf launcher directories — those
    that actually contain VASP (or other calc) files rather than just
    more nested launchers.

    Returns a list of (leaf_abs_path, leaf_dirname) tuples.
    """
    leaves = []
    for root, dirs, files in os.walk(block_path):
        dir_type = get_dir_type(files)
        if dir_type:
            leaves.append(root)
            dirs[:] = []  # don't descend into relax1/relax2 etc.
    return leaves


def unique_launcher_name(dest_dir, name):
    """
    Given a destination directory and a desired launcher name, return a name
    that doesn't collide with anything already in dest_dir. Appends _1, _2, etc.
    if needed.
    """
    candidate = name
    counter = 1
    while os.path.exists(os.path.join(dest_dir, candidate)):
        candidate = f"{name}_{counter}"
        counter += 1
    return candidate


def reorganize_blocks(block_launchers, base_path, max_per_block=50):
    """
    Reorganize blocks so that:
      1. Arbitrary launcher nesting is flattened to block_/launcher_/
      2. No block has more than max_per_block launchers.

    Each leaf launcher (the directory actually containing VASP files) is
    moved directly under a block directory. The nested hierarchy is not
    preserved.

    Args:
        block_launchers: dict mapping block name -> list of launcher paths
        base_path: the root directory containing the blocks
        max_per_block: maximum number of launchers per block

    Returns:
        A new block_launchers dict reflecting the reorganized layout.
    """
    import time

    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]

    # First pass: discover all leaf launchers across all blocks
    all_leaves = []  # list of (current_abs_path, leaf_name, original_block)
    for block in block_launchers:
        block_path = os.path.join(base_path, block)
        for leaf_path in find_leaf_launchers(block_path):
            leaf_name = os.path.basename(leaf_path)
            all_leaves.append((leaf_path, leaf_name, block))

    logger.info(
        f"Found {len(all_leaves)} leaf launchers across "
        f"{len(block_launchers)} block(s). Flattening and redistributing "
        f"into blocks of {max_per_block}..."
    )

    # Chunk all leaves into groups of max_per_block
    leaf_chunks = chunks(all_leaves, max_per_block)
    new_block_launchers = {}

    for chunk in leaf_chunks:
        new_block = get_timestamp_dir(prefix="block")
        new_block_dir = os.path.join(base_path, new_block)
        chunk_launcher_names = []

        if run:
            os.makedirs(new_block_dir, exist_ok=True)

        for leaf_path, leaf_name, orig_block in chunk:
            dest_name = unique_launcher_name(new_block_dir, leaf_name)
            dst = os.path.join(new_block_dir, dest_name)

            if run:
                os.rename(leaf_path, dst)
                logger.debug(
                    f"  {orig_block}/.../{leaf_name} -> {new_block}/{dest_name}"
                )
            else:
                logger.debug(
                    f"  Would move {orig_block}/.../{leaf_name} -> "
                    f"{new_block}/{dest_name}"
                )

            chunk_launcher_names.append(dest_name)

        new_block_launchers[new_block] = chunk_launcher_names
        logger.info(
            f"  {'Created' if run else 'Would create'} {new_block} "
            f"with {len(chunk)} launchers"
        )
        time.sleep(0.1)  # ensure unique timestamp-based block names

    # Clean up empty old block directories
    for block in block_launchers:
        block_path = os.path.join(base_path, block)
        if run:
            # remove the now-empty tree (only empty dirs should remain)
            try:
                shutil.rmtree(block_path)
                logger.debug(f"  Removed empty original block {block}")
            except OSError as e:
                logger.warning(f"  Could not remove {block}: {e}")
        else:
            logger.debug(f"  Would remove empty original block {block}")

    return new_block_launchers
