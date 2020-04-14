import os
import stat
import mgzip
import click
import logging
import itertools

from datetime import datetime
from functools import update_wrapper
from slurmpy import Slurm
from glob import glob
from shutil import copyfile, rmtree
from fnmatch import fnmatch
from datetime import datetime
from collections import defaultdict
from pymatgen import Structure
from atomate.vasp.database import VaspCalcDb
from fireworks.fw_config import FW_BLOCK_FORMAT
from mongogrant.client import Client

from emmet.core.utils import group_structures
from emmet.cli.config import exclude, base_query, aggregation_keys
from emmet.cli.config import structure_keys, log_fields, tracker

logger = logging.getLogger("emmet")
perms = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP


class EmmetCliError(Exception):
    pass


def structures_match(s1, s2):
    return bool(len(list(group_structures([s1, s2]))) == 1)


def ensure_indexes(indexes, colls):
    created = defaultdict(list)
    for index in indexes:
        for coll in colls:
            keys = [k.rsplit("_", 1)[0] for k in coll.index_information().keys()]
            if index not in keys:
                coll.ensure_index(index)
                created[coll.full_name].append(index)
    return created


def calcdb_from_mgrant(spec):
    client = Client()
    role = "rw"  # NOTE need write access to source to ensure indexes
    host, dbname_or_alias = spec.split("/", 1)
    auth = client.get_auth(host, dbname_or_alias, role)
    if auth is None:
        raise Exception("No valid auth credentials available!")
    return VaspCalcDb(
        auth["host"],
        27017,
        auth["db"],
        "tasks",
        auth["username"],
        auth["password"],
        authSource=auth["db"],
    )


def get_meta_from_structure(struct):
    d = {"formula_pretty": struct.composition.reduced_formula}
    d["nelements"] = len(set(struct.composition.elements))
    d["nsites"] = len(struct)
    d["is_ordered"] = struct.is_ordered
    d["is_valid"] = struct.is_valid()
    return d


def aggregate_by_formula(coll, q, key=None):
    query = {"$and": [q, exclude]}
    query.update(base_query)
    nested = False
    if key is None:
        for k in aggregation_keys:
            q = {k: {"$exists": 1}}
            q.update(base_query)
            doc = coll.find_one(q)
            if doc:
                key = k
                nested = int("snl" in doc)
                break
        else:
            raise ValueError(
                f"could not find one of the aggregation keys {aggregation_keys} in {coll.full_name}!"
            )

    push = {k.split(".")[-1]: f"${k}" for k in structure_keys[nested]}
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


def get_subdir(dn):
    return dn.rsplit(os.sep, 1)[-1]


def get_timestamp_dir(prefix="launcher"):
    time_now = datetime.utcnow().strftime(FW_BLOCK_FORMAT)
    return "_".join([prefix, time_now])


def is_vasp_dir(list_of_files):
    for f in list_of_files:
        if f.startswith("INCAR"):
            return True


def make_block(base_path):
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    block = get_timestamp_dir(prefix="block")
    block_dir = os.path.join(base_path, block)
    if run:
        os.mkdir(block_dir)
    return block_dir


def get_symlinked_path(root, base_path_index):
    """organize directory in block_*/launcher_* via symbolic links"""
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
            if len(glob(p)) < 300:
                break
        else:
            # didn't find a block with < 300 launchers
            block_dir = make_block(base_path, run)

    if root_split[-1].startswith("launcher_"):
        launch_dir = os.path.join(block_dir, root_split[-1])
        if not os.path.exists(launch_dir):
            if run:
                os.rename(root, launch_dir)
            logger.debug(f"{root} -> {launch_dir}")
    else:
        launch = get_timestamp_dir(prefix="launcher")
        launch_dir = os.path.join(block_dir, launch)
        if run:
            os.rename(root, launch_dir)
            os.symlink(launch_dir, root)
        logger.debug(f"{root} -> {launch_dir}")

    return launch_dir


def create_orig_inputs(vaspdir):
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    for inp in ["INCAR", "KPOINTS", "POTCAR", "POSCAR"]:
        input_path = os.path.join(vaspdir, inp)
        if not glob(input_path + ".orig*"):
            matches = glob(input_path + "*")
            if matches:
                input_path = matches[0]
                orig_path = input_path.replace(inp, inp + ".orig")
                if run:
                    copyfile(input_path, orig_path)
                logger.debug(f"{input_path} -> {orig_path}")


def get_vasp_dirs():
    ctx = click.get_current_context()
    run = ctx.parent.parent.params["run"]
    pattern = ctx.parent.params["pattern"]
    base_path = ctx.parent.params["directory"].rstrip(os.sep)
    base_path_index = len(base_path.split(os.sep))
    if pattern:
        pattern_split = pattern.split(os.sep)
        pattern_split_len = len(pattern_split)

    for root, dirs, files in os.walk(base_path, topdown=True):
        level = len(root.split(os.sep)) - base_path_index
        if pattern and dirs and pattern_split_len > level:
            p = pattern_split[level]
            dirs[:] = [d for d in dirs if fnmatch(d, p)]

        for d in dirs:
            dn = os.path.join(root, d)
            st = os.stat(dn)
            if not bool(st.st_mode & perms):
                raise EmmetCliError(f"Insufficient permissions {st.st_mode} for {dn}.")

        if is_vasp_dir(files):
            with click.progressbar(files, label="Check permissions & gzip") as bar:
                for f in bar:
                    fn = os.path.join(root, f)
                    st = os.stat(fn)
                    if not bool(st.st_mode & perms):
                        raise EmmetCliError(
                            f"Insufficient permissions {st.st_mode} for {fn}."
                        )
                    if run and not f.endswith(".gz") and not os.path.exists(fn + ".gz"):
                        with open(fn, "rb") as fo, mgzip.open(
                            fn + ".gz", "wb", thread=0
                        ) as fw:
                            fw.write(fo.read())
                        os.remove(fn)

            vasp_dir = get_symlinked_path(root, base_path_index)
            create_orig_inputs(vasp_dir)
            dirs[:] = []  # don't descend further (i.e. ignore relax1/2)
            logger.info(vasp_dir)
            yield vasp_dir


def reconstruct_command(sbatch=False):
    ctx = click.get_current_context()
    command = []
    for cmd, params in zip(ctx.command_path.split(), [
        ctx.grand_parent.params, ctx.parent.params, ctx.params
    ]):
        command.append(cmd)
        for k, v in params.items():
            if v:
                if isinstance(v, bool):
                    if (sbatch and k != 'sbatch') or not sbatch:
                        command.append(f"--{k}")
                elif isinstance(v, str):
                    command.append(f"--{k}=\"{v}\"")
                else:
                    command.append(f"--{k}={v}")

    return " ".join(command)


def track(func):
    """decorator to track command in GH issue / gists"""
    def wrapper(*args, **kwargs):
        ret = func(*args, **kwargs)
        ctx = click.get_current_context()
        run = ctx.grand_parent.params["run"]

        if run and ret:
            logger.info(ret)
            command = reconstruct_command()
            gh = ctx.grand_parent.obj["GH"]
            now = str(datetime.now()).replace(" ", "-")
            fn = ctx.command_path.replace(" ", "-") + f"_{now}.log"
            logs = ctx.grand_parent.obj["LOG_STREAM"]
            files = {fn: {"content": logs.getvalue()}}
            gist = gh.create_gist(command, files, public=False)
            logger.info(gist.html_url)
            issue_number = ctx.grand_parent.params["issue"]
            issue = gh.issue(tracker["org"], tracker["repo"], issue_number)
            txt = f"*{ctx.command_path}* returned \"{ret}\" "
            txt += f"([logs]({gist.html_url})):\n\n```\n{command}\n```"
            comment = issue.create_comment(txt)
            logger.info(comment.html_url)

    return update_wrapper(wrapper, func)


def sbatch(func):
    """decorator to enable SLURM mode on command"""
    @track
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context()
        ctx.grand_parent = ctx.parent.parent
        if not ctx.grand_parent.params["sbatch"]:
            return ctx.invoke(func, *args, **kwargs)

        run = ctx.grand_parent.params["run"]
        if run:
            click.secho(f"SBATCH MODE! Submitting to SLURM queue.", fg="green")

        directory = ctx.parent.params.get("directory")
        if not directory:
            raise EmmetCliError(f"{ctx.parent.command_path} needs --directory option!")

        track_dir = os.path.join(directory, '.emmet')
        if run and not os.path.exists(track_dir):
            os.mkdir(track_dir)
            logger.debug(f"{track_dir} created")

        s = Slurm(
            ctx.command_path.replace(" ", "-"),
            slurm_kwargs={
                "qos": "xfer",
                "time": "48:00:00",
                "licenses": "SCRATCH"
            },
            date_in_name=False,
            scripts_dir=track_dir,
            log_dir=track_dir,
            bash_strict=False,
        )

        command = reconstruct_command(sbatch=True)
        return s.run(command, _cmd="sbatch" if run else "ls")

    return update_wrapper(wrapper, func)
