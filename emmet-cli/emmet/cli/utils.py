import itertools
import logging
import multiprocessing
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
from botocore.exceptions import EndpointConnectionError
from dotty_dict import dotty
from fireworks.fw_config import FW_BLOCK_FORMAT
from mongogrant.client import Client
from pymatgen.core import Structure
from pymatgen.util.provenance import StructureNL
from pymongo.errors import DocumentTooLarge
from emmet.core.tasks import TaskDoc
from emmet.core.utils import utcnow
from emmet.core.vasp.validation import ValidationDoc
from emmet.cli.db import TaskStore
from pymatgen.entries.compatibility import MaterialsProject2020Compatibility

from emmet.cli import SETTINGS
from emmet.core.utils import group_structures

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


def calcdb_from_mgrant(spec_or_dbfile):
    if os.path.exists(spec_or_dbfile):
        return TaskStore.from_db_file(spec_or_dbfile)

    client = Client()
    role = "rw"  # NOTE need write access to source to ensure indexes
    host, dbname_or_alias = spec_or_dbfile.split("/", 1)
    auth = client.get_auth(host, dbname_or_alias, role)
    if auth is None:
        raise Exception("No valid auth credentials available!")
    return TaskStore(
        store_kwargs={
            "host": auth["host"],
            "port": 27017,
            "database": auth["db"],
            "collection": "tasks",
            "user": auth["username"],
            "password": auth["password"],
            "authSource": auth["db"],
        }
    )


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
                    shutil.copyfile(input_path, orig_path)
                logger.debug(f"{input_path} -> {orig_path}")


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
            if dir_type == "vasp":
                create_orig_inputs(vasp_dir)

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


def parse_vasp_dirs(vaspdirs, tag, task_ids, snl_metas):  # noqa: C901
    process = multiprocessing.current_process()
    name = process.name
    chunk_idx = int(name.rsplit("-")[1]) - 1
    logger.info(f"{name} starting.")
    tags = [tag, SETTINGS.year_tags[-1]]
    ctx = click.get_current_context()
    spec_or_dbfile = ctx.parent.parent.params["spec_or_dbfile"]
    target = calcdb_from_mgrant(spec_or_dbfile)
    snl_collection = target.db.snls_user
    sbxn = list(filter(None, target.collection.distinct("sbxn")))
    logger.info(f"Using sandboxes {sbxn}.")
    no_dupe_check = ctx.parent.parent.params["no_dupe_check"]
    run = ctx.parent.parent.params["run"]
    projection = {"tags": 1, "task_id": 1}
    # projection = {"tags": 1, "task_id": 1, "calcs_reversed": 1}
    count = 0

    # fs_keys = ["bandstructure", "dos", "chgcar", "locpot", "elfcar"]
    # for i in range(3):
    #    fs_keys.append(f"aeccar{i}")

    for vaspdir in vaspdirs:
        logger.info(f"{name} VaspDir: {vaspdir}")
        launcher = get_subdir(vaspdir)
        query = {"dir_name": {"$regex": launcher}}
        manual_taskid = isinstance(task_ids, dict)
        docs = list(
            target.collection.find(query, projection).sort([("_id", -1)]).limit(1)
        )

        if docs:
            if no_dupe_check:
                logger.warning(f"FORCING re-parse of {launcher}!")
                if not manual_taskid:
                    raise ValueError("need --task-ids when re-parsing!")
            else:
                if run:
                    shutil.rmtree(vaspdir)
                    logger.warning(f"{name} {launcher} already parsed -> removed.")
                else:
                    logger.warning(f"{name} {launcher} already parsed -> would remove.")
                continue

        additional_fields = {"sbxn": sbxn, "tags": []}
        snl_metas_avail = isinstance(snl_metas, dict)
        task_id = (
            task_ids.get(launcher) if manual_taskid else task_ids[chunk_idx][count]
        )

        if not task_id:
            logger.error(f"Unable to determine task_id for {launcher}")
            continue

        additional_fields["task_id"] = task_id
        logger.info(f"Using {task_id} for {launcher}.")

        if docs:
            # make sure that task gets the same tags as the previously parsed task
            # (run through set to implicitly remove duplicate tags)
            if docs[0]["tags"]:
                existing_tags = list(set(docs[0]["tags"]))
                additional_fields["tags"] += existing_tags
                logger.info(f"Adding existing tags {existing_tags} to {tags}.")

        try:
            task_doc = TaskDoc.from_directory(
                dir_name=vaspdir,
                additional_fields=additional_fields,
                volumetric_files=ctx.params["store_volumetric_data"],
                task_names=ctx.params["runs"],
            )
        except Exception as ex:
            logger.error(f"Failed to build a TaskDoc from {vaspdir}: {ex}")
            continue

        try:
            validation_doc = ValidationDoc.from_task_doc(task_doc)
        except Exception as exc:
            logger.error(f"Unable to construct a valid ValidationDoc: {exc}")
            continue

        if not validation_doc.valid:
            logger.error(f"Not valid: {validation_doc.reasons}")
            continue

        if validation_doc.warnings:
            logger.warn(validation_doc.warnings)

        try:
            entry = MaterialsProject2020Compatibility().process_entry(
                task_doc.structure_entry
            )
        except Exception as exc:
            logger.error(f"Unable to apply corrections: {exc}")
            continue

        snl_dct = None
        if snl_metas_avail:
            snl_meta = snl_metas.get(launcher)
            if snl_meta:
                references = snl_meta.get("references")
                authors = snl_meta.get(
                    "authors", ["Materials Project <feedback@materialsproject.org>"]
                )
                kwargs = {"projects": [tag]}
                if references:
                    kwargs["references"] = references

                struct = task_doc.input.structure
                snl = StructureNL(struct, authors, **kwargs)
                snl_dct = snl.as_dict()
                snl_dct.update(get_meta_from_structure(struct))
                snl_id = snl_meta["snl_id"]
                snl_dct["snl_id"] = snl_id
                logger.info(f"Created SNL object for {snl_id}.")

        if run:
            if task_doc.state == "successful":
                if docs and no_dupe_check:
                    # new_calc = task_doc["calcs_reversed"][0]
                    # existing_calc = docs[0]["calcs_reversed"][0]
                    # print(existing_calc.keys())

                    # for fs_key in fs_keys:
                    #    print(fs_key)
                    #    fs_id_key = f"{fs_key}_fs_id"
                    #    if fs_id_key in existing_calc:
                    #        if fs_id_key in new_calc:
                    #            # NOTE the duplicate fs_id / s3 object has already been
                    #            # created in the drone though
                    #            raise NotImplementedError(
                    #                f"Missing duplicate check to decide on overwriting {key}_fs_id"
                    #            )

                    #        for k in [fs_id_key, f"{key}_compression"]:
                    #            new_calc[k] = existing_calc[k]

                    #        print(fs_id_key, task_doc["calcs_reversed"][0][fs_id_key])  # TODO CHECK
                    target.collection.delete_one({"task_id": task_id})
                    logger.warning(f"Removed previously parsed task {task_id}!")

                # return count  # TODO remove

                try:
                    target.insert_task(task_doc.model_dump(), use_gridfs=True)
                except EndpointConnectionError as exc:
                    logger.error(f"Connection failed for {task_id}: {exc}")
                    continue
                except DocumentTooLarge:
                    output = dotty(task_doc.calcs_reversed[0].output.as_dict())
                    pop_keys = [
                        "normalmode_eigenvecs",
                        "force_constants",
                        "outcar.onsite_density_matrices",
                    ]

                    for k in pop_keys:
                        if k not in output:
                            continue

                        logger.warning(f"{name} Remove {k} and retry ...")
                        output.pop(k)
                        try:
                            target.insert_task(task_doc, use_gridfs=True)
                            break
                        except DocumentTooLarge:
                            continue
                    else:
                        logger.warning(f"{name} failed to reduce document size")
                        continue
                except Exception as ex:
                    logger.error(f"{name} failed to insert: {ex}")
                    continue

                if target.collection.count_documents(query):
                    if snl_dct:
                        result = snl_collection.insert_one(snl_dct)
                        logger.info(
                            f"SNL {result.inserted_id} inserted into {snl_collection.full_name}."
                        )

                    shutil.rmtree(vaspdir)
                    logger.info(f"{name} Successfully parsed and removed {launcher}.")
                    count += 1
        else:
            count += 1

    return count
