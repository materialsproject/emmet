import hashlib
import itertools
import json
import logging
import multiprocessing
import os
import shutil
import stat

import tarfile
import time
from _hashlib import HASH as Hash
from enum import Enum
from fnmatch import fnmatch

from datetime import datetime
from collections import defaultdict
from glob import glob
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from typing import Union
from urllib.parse import urlparse
from zipfile import ZipFile, ZIP_DEFLATED

import click
import mgzip

from datetime import datetime
from collections import defaultdict
from pymatgen.core import Structure
from pymatgen.util.provenance import StructureNL

from datetime import datetime
from collections import defaultdict
from pymatgen.core import Structure
from pymatgen.util.provenance import StructureNL
from atomate.vasp.database import VaspCalcDb
from atomate.vasp.drones import VaspDrone

from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient, Authenticator
import requests
from dotty_dict import dotty

from fireworks.fw_config import FW_BLOCK_FORMAT
from keycloak import KeycloakOpenID
from maggma.core.store import Sort
from maggma.stores.advanced_stores import MongograntStore
from mongogrant.client import Client
from pymatgen.util.provenance import StructureNL


from pydantic import BaseModel, Field
from pymatgen import Structure
from pymongo.errors import DocumentTooLarge
from tqdm import tqdm


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
    SUBMITTED = "submitted to SLURM"


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

    if created:
        indexes = ", ".join(created[coll.full_name])
        logger.debug(f"Created the following index(es) on {coll.full_name}:\n{indexes}")


def calcdb_from_mgrant(spec_or_dbfile):
    if os.path.exists(spec_or_dbfile):
        return VaspCalcDb.from_db_file(spec_or_dbfile)

    client = Client()
    role = "rw"  # NOTE need write access to source to ensure indexes
    host, dbname_or_alias = spec_or_dbfile.split("/", 1)
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
    return [lst[i: i + n] for i in range(0, len(lst), n)]


def get_subdir(dn):
    return dn.rstrip(os.sep).rsplit(os.sep, 1)[-1]


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
            block_dir = make_block(base_path)

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
    run = ctx.parent.parent.params["run"]
    nmax = ctx.parent.params["nmax"]
    pattern = ctx.parent.params["pattern"]
    reorg = ctx.parent.params["reorg"]

    base_path = ctx.parent.params["directory"].rstrip(os.sep)
    base_path_index = len(base_path.split(os.sep))
    if pattern:
        pattern_split = pattern.split(os.sep)
        pattern_split_len = len(pattern_split)

    counter = 0
    for root, dirs, files in os.walk(base_path, topdown=True):
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

        if is_vasp_dir(files):
            gzipped = False
            for f in files:
                fn = os.path.join(root, f)
                if os.path.islink(fn):
                    if run:
                        os.unlink(fn)
                        logger.warning(f"Unlinked {fn}.")
                    else:
                        logger.warning(f"Would unlink {fn}.")
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

                    os.remove(fn)  # remove original
                    shutil.chown(fn_gz, group="matgen")
                    gzipped = True

            # NOTE skip symlink'ing on MP calculations from the early days
            vasp_dir = get_symlinked_path(root, base_path_index) if reorg else root
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
    drone = VaspDrone(
        additional_fields={"tags": tags},
        store_volumetric_data=ctx.params["store_volumetric_data"],
    )
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

        try:
            task_doc = drone.assimilate(vaspdir)
        except Exception as ex:
            logger.error(f"Failed to assimilate {vaspdir}: {ex}")
            continue

        task_doc["sbxn"] = sbxn

        manual_taskid = isinstance(task_ids, dict)

        snl_metas_avail = isinstance(snl_metas, dict)
        task_id = task_ids[launcher] if manual_taskid else task_ids[chunk_idx][count]
        task_doc["task_id"] = task_id
        logger.info(f"Using {task_id} for {launcher}.")

        if docs:
            # make sure that task gets the same tags as the previously parsed task
            # (run through set to implicitly remove duplicate tags)
            if docs[0]["tags"]:
                existing_tags = list(set(docs[0]["tags"]))
                task_doc["tags"] += existing_tags
                logger.info(f"Adding existing tags {existing_tags} to {tags}.")

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

                struct = Structure.from_dict(task_doc["input"]["structure"])
                snl = StructureNL(struct, authors, **kwargs)
                snl_dct = snl.as_dict()
                snl_dct.update(get_meta_from_structure(struct))
                snl_id = snl_meta["snl_id"]
                snl_dct["snl_id"] = snl_id
                logger.info(f"Created SNL object for {snl_id}.")

        snl_dct = None
        if snl_metas_avail:
            snl_meta = snl_metas.get(launcher)
            if snl_meta:
                references = snl_meta.get("references")
                authors = snl_meta.get("authors", ["Materials Project <feedback@materialsproject.org>"])
                kwargs = {"projects": [tag]}
                if references:
                    kwargs["references"] = references

                struct = Structure.from_dict(task_doc["input"]["structure"])
                snl = StructureNL(struct, authors, **kwargs)
                snl_dct = snl.as_dict()
                snl_dct.update(get_meta_from_structure(struct))
                snl_id = snl_meta["snl_id"]
                snl_dct["snl_id"] = snl_id
                logger.info(f"Created SNL object for {snl_id}.")

        if run:
            if task_doc["state"] == "successful":
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
                    target.collection.remove({"task_id": task_id})
                    logger.warning(f"Removed previously parsed task {task_id}!")

                # return count  # TODO remove

                try:
                    target.insert_task(task_doc, use_gridfs=True)
                except DocumentTooLarge:
                    output = dotty(task_doc["calcs_reversed"][0]["output"])
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

                if target.collection.count(query):
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


def make_tar_file(output_dir: Path, output_file_name: str, source_dir: Path):
    if not output_file_name.endswith(".tar.gz"):
        output_file_name = output_file_name + ".tar.gz"
    if output_dir.exists() is False:
        output_dir.mkdir(parents=True, exist_ok=True)
    output_tar_file = output_dir / output_file_name

    if output_tar_file.exists() is False:
        with tarfile.open(output_tar_file.as_posix(), "w:gz") as tar:
            tar.add(source_dir.as_posix(), arcname=os.path.basename(source_dir.as_posix()))


def compress_launchers(input_dir: Path, output_dir: Path, launcher_paths: List[str]):
    """

    create directories & zip

    :param input_dir:
    :param output_dir:
    :param block_name:
    :param launcher_paths:
    :return:
    """

    for launcher_path in launcher_paths:
        out_dir = Path(output_dir) / Path(launcher_path).parent
        output_file_name = launcher_path.split("/")[-1]
        if (out_dir / output_file_name).exists():
            continue
        else:
            logger.info(f"Compressing {launcher_path}".strip())
            make_tar_file(output_dir=out_dir,
                          output_file_name=output_file_name,
                          source_dir=Path(input_dir) / launcher_path)


def find_un_uploaded_materials_task_id(gdrive_mongo_store: MongograntStore,
                                       material_mongo_store: MongograntStore,
                                       max_num: int = 1000) -> List[str]:
    """
    Given mongo stores, find the next max_num mp_ids that are not yet uploaded.

    :param gdrive_mongo_store: gdrive mongo store
    :param material_mongo_store: materials mongo store
    :param max_num: int, maximum number of materials to return
    :return:
        list of materials that are not uploaded
    """
    # get a ALL task ids, sorted in earliest material order
    # find which ones are not uploaded
    task_ids: Dict[str, None] = find_task_ids_sorted(material_mongo_store)
    gdrive_results = gdrive_mongo_store.query(criteria={"task_id": {"$in": list(task_ids)}},
                                              properties={"task_id": 1})
    uploaded_task_ids = set(gdrive_result["task_id"] for gdrive_result in gdrive_results)
    for k in uploaded_task_ids:
        task_ids.pop(k, None)
    # task_ids at this point contain un-uploaded keys, sorted in order of materials update date
    result: List[str] = list(task_ids.keys())[:max_num]
    return result


def find_task_ids_sorted(material_mongo_store: MongograntStore) -> Dict[str, None]:
    result: Dict[str, None] = dict()
    materials = material_mongo_store.query(
        criteria={"deprecated": False},
        properties={"task_id": 1, "blessed_tasks": 1, "last_updated": 1},
        sort={"last_updated": Sort.Descending})
    for material in materials:
        if "blessed_tasks" in material:
            blessed_tasks: dict = material["blessed_tasks"]
            task_ids = list(blessed_tasks.values())
            result.update(dict.fromkeys(task_ids))
    return result


def find_material_task_ids(material_mongo_store) -> Dict[str, List[str]]:
    materials = material_mongo_store.query(
        criteria={"deprecated": False},
        properties={"task_id": 1, "blessed_tasks": 1, "last_updated": 1},
        sort={"last_updated": Sort.Descending})
    materials_task_id_dict: Dict[str, List[str]] = dict()
    for material in materials:
        if "blessed_tasks" in material:
            blessed_tasks: dict = material["blessed_tasks"]
            materials_task_id_dict[material["task_id"]] = list(blessed_tasks.values())
    return materials_task_id_dict


class GDriveLog(BaseModel):
    path: str = Field(..., title="Path for the file",
                      description="Should reflect both local disk space AND google drive path")
    last_updated: datetime = Field(default=datetime.now())
    task_id: str = Field(default="", title="Material ID in which this launcher belongs to")
    file_size: int = Field(default=0, description="file size of the tar.gz")
    md5hash: str = Field(default="", description="md5 hash of the content of the files inside this gzip")
    files: List[Dict[str, Any]] = Field(default=[], description="meta data of the content of the gzip")
    nomad_updated: Optional[datetime] = Field(default=None)
    nomad_upload_id: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)


class File(BaseModel):
    file_name: str = Field(default="")
    size: int = Field(default=0)
    md5hash: str = Field(default="")


def move_dir(src: str, dst: str, pattern: str):
    """
    Move entire directory matching pattern from src to dst
    :param src: src location
    :param dst: dst location
    :param pattern: folder patterns
    :return:
        none
    """
    for file_path in glob(f'{src}/{pattern}'):
        logger.info(f"Moving [{file_path}] to [{dst}]")
        try:
            shutil.copy(src=file_path, dst=f"{dst}")
        except Exception as e:
            logger.warning(e)
            logger.info("not moving this directory because it already existed for some reason.")


def nomad_find_not_uploaded(gdrive_mongo_store: MongograntStore, num: int) -> List[List[str]]:
    """
    find a list of tasks that are not uploaded to nomad, sort ascending based on date created. limit by num.
    chunk those list of tasks into 10 chunks for later multi processing.

    if num < 0, return 32 GB worth of materials in each chunk

    :param gdrive_mongo_store:
    :param num: number of launchers to find
    :return:
        List of chunks with a total of n launchers or each with max 32 GB of launchers file path
    """

    # fetch meta data of un-uploaded launchers from GDrive
    if num >= 0:
        raw = gdrive_mongo_store.query(
            criteria={"$and": [{"nomad_updated": None}, {"error": None}]},
            properties={"task_id": 1, "file_size": 1},
            sort={"last_updated": Sort.Ascending},
            limit=num
        )
    else:
        raw = gdrive_mongo_store.query(
            criteria={"$and": [{"nomad_updated": None}, {"error": None}]},
            properties={"task_id": 1, "file_size": 1},
            sort={"last_updated": Sort.Ascending}
        )

    meta_datas = [r for r in raw]
    single_max_nomad_upload_size = 31 * 1e9  # max is 32 gb, but im going to play it really safe
    tmp_results: Dict[int, List[str]] = dict()
    total_size = 0
    result_counter = 0
    curr_size = 0
    max_chunks = 10

    # loop through all meta data, fill in each chunk with as much data as possible
    for meta_data in meta_datas:
        if result_counter >= max_chunks:
            break
        else:
            file_size = meta_data["file_size"]
            task_id = meta_data["task_id"]
            if curr_size + file_size >= single_max_nomad_upload_size:
                curr_size = 0
                result_counter += 1
            else:
                l = tmp_results.get(result_counter, [])
                l.append(task_id)
                tmp_results[result_counter] = l
                curr_size += file_size
                total_size += file_size

    # expand the dictionary to a list
    results = [result for result in tmp_results.values()]

    logger.info(f"Prepared [{len(results)}] chunks with [{sum([len(r) for r in results])}] items [{total_size}] bytes")
    return results


def nomad_upload_data(task_ids: List[str], username: str,
                      password: str, gdrive_mongo_store: MongograntStore,
                      root_dir: Path, name="thread_1"):
    """
    it is gaurenteed that sum of the file_size of the task_ids is less than 32 gb.

    :param name: name of this upload
    :param task_ids: task_ids to upload
    :param username: username of nomad
    :param password: password of nomad
    :param gdrive_mongo_store: gdrive mongo store connection
    :param root_dir: root dir to upload
    :return:
        True of upload success
        None or False otherwise
    """
    logger.info(f"[{name}] start processing [{len(task_ids)}] tasks")
    try:
        # create the bravado client and establish credential
        nomad_url = 'http://nomad-lab.eu/prod/rae/api'
        http_client = RequestsClient()
        http_client.authenticator = KeycloakAuthenticator(user=username, password=password, nomad_url=nomad_url)
        client: SwaggerClient = SwaggerClient.from_url('%s/swagger.json' % nomad_url, http_client=http_client)
    except Exception as e:
        logger.error(f"[{name}] Unable to get credential: {e}")
        return False

    try:
        raw = gdrive_mongo_store.query(criteria={"task_id": {"$in": task_ids}})
        records: List[GDriveLog] = [GDriveLog.parse_obj(record) for record in raw]
    except Exception as e:
        logger.error(f"[{name}] failed to fetch data from mongo store: {e}")
        return False

    try:
        # prepare upload data
        upload_preparation_dir = root_dir / Path(f"nomad_upload_{name}")
        if not upload_preparation_dir.exists():
            upload_preparation_dir.mkdir(parents=True, exist_ok=True)
        if upload_preparation_dir.exists():
            # this should NOT exist, if it exist, that means previous upload probably failed,
            # and for some reason it did not make sure to clean up after itself.
            # Forcefully clean this directory
            _nomad_clean_up(upload_preparation_dir, None)
            upload_preparation_dir.mkdir(parents=True, exist_ok=True)

        # organize_data
        nomad_json, untar_source_file_path_to_arcname_map = nomad_organize_data(task_ids=task_ids, records=records,
                                                                                root_dir=root_dir,
                                                                                upload_preparation_dir=
                                                                                upload_preparation_dir,
                                                                                name=name)
    except Exception as e:
        logger.error(f"[{name}] failed to prepare upload data: {e}")
        return False

    try:
        # write json data to file
        write_json(upload_preparation_dir=upload_preparation_dir, nomad_json=nomad_json, name=name)

        # un-tar.gz the files
        zipped_upload_preparation_file_path = write_zip_from_targz(upload_preparation_dir=upload_preparation_dir,
                                                                   untar_source_file_path_to_arcname_map=
                                                                   untar_source_file_path_to_arcname_map,
                                                                   name=name)
    except Exception as e:
        logger.error(f"[{name}] failed to write json and re-zip data: {e}")
        _nomad_clean_up(upload_preparation_dir, None)
        return False
    # try:
    #     # upload to nomad
    #     logger.info(f"[{name}] Start Uploading [{zipped_upload_preparation_file_path}]"
    #                 f"[{os.path.getsize(zipped_upload_preparation_file_path)} bytes] to NOMAD")
    #     user = client.auth.get_auth().response().result
    #     token = user.access_token
    #     url = nomad_url + '/uploads/?publish_directly=true'
    #     with open(zipped_upload_preparation_file_path, 'rb') as f:
    #         response = requests.put(url=url, headers={'Authorization': 'Bearer %s' % token}, data=f)
    #     upload_id = response.json()['upload_id']
    #     if response.status_code == 200:
    #         logger.info(f"[{name}] is done uploading. Upload ID = [{upload_id}]")
    #         upload_completed = True
    #     else:
    #         upload_completed = False
    #         logger.error(f'Upload [{upload_id}] failed with code [{response.json()}]')
    #         from urllib.error import HTTPError
    #         raise HTTPError(url=response.url,
    #                         code=response.status_code,
    #                         msg=f'Upload [{upload_id}] failed with code [{response.json()}]',
    #                         hdrs=response.headers,
    #                         fp=None)
    # except Exception as e:
    #     logger.error(f"[{name}] Failed to upload to NOMAD: {e}. Removing data generated.")
    #     # _nomad_clean_up(upload_preparation_dir, Path(zipped_upload_preparation_file_path))
    #     return False

    # try:
    #     # update mongo store
    #     if upload_completed:
    #         for record in records:
    #             record.nomad_updated = datetime.now()
    #             record.nomad_upload_id = upload_id
    #         gdrive_mongo_store.update(docs=[record.dict() for record in records], key="task_id")
    # except Exception as e:
    #     logger.error(f"[{name}] Failed to log to mongo store: {e}. Removing data generated.")
    #     _nomad_clean_up(upload_preparation_dir, Path(zipped_upload_preparation_file_path))
    #     return False
    # try:
    #     _nomad_clean_up(upload_preparation_dir, Path(zipped_upload_preparation_file_path))
    # except Exception as e:
    #     logger.error(f"[{name}] Failed to clean up: {e}")

    return upload_completed


def _nomad_clean_up(upload_preparation_dir: Optional[Path], zipped_upload_preparation_file_path: Optional[Path]):
    if upload_preparation_dir is not None and upload_preparation_dir.exists():
        shutil.rmtree(upload_preparation_dir.as_posix())
    if zipped_upload_preparation_file_path is not None and zipped_upload_preparation_file_path.exists():
        os.remove(zipped_upload_preparation_file_path.as_posix())


def nomad_organize_data(task_ids, records, root_dir: Path, upload_preparation_dir: Path, name):
    # loop over records, generate json information
    nomad_json: dict = {"comment": f"Materials Project Upload at {datetime.now()}",
                        "external_db": "Materials Project",
                        "entries": dict()}
    # populate json
    untar_source_file_path_to_arcname_map: List[
        Tuple[str, str]] = list()  # list of (full_path/launcher-xyz.tar.gz launcher-xyz.tar.gz)
    logger.info(f"[{name}] Organizing {len(task_ids)} launchers")

    """
    for every record, build a entry in our log later used to populate nomad.json
    nomad.json will look like:
    {
    "comment": "Data from a cool external project",
    "external_db": "Materials Project",
    "entries": {
        "block_2017-11-15-20-03-23-693030/launcher_2017-11-18-00-38-32-702369/launcher_2017-11-18-02-22-11-552158/vasprun.xml.gz" : {
            "external_id" : "michael-2",
            "references": ["https://materialsproject.org/tasks/michael-2/"]
            },
            ...
        }
    }
    """
    for record in tqdm(records):
        full_path_without_suffix: Path = root_dir / record.path
        full_file_path: Path = (root_dir / (record.path + ".tar.gz"))
        if not full_file_path.exists():
            record.error = f"Record can no longer be found in {full_file_path}"
            logger.info(f"[{name}] File not found: Record can no longer be found in {full_file_path}")
        else:
            my_tar = tarfile.open(full_file_path.as_posix(), "r")
            file_names = my_tar.getnames()
            vasp_run_names = [name for name in file_names if "vasprun" in name]
            vasp_run_name = Path(vasp_run_names[0]).name
            external_id = record.task_id
            references = [f"https://materialsproject.org/tasks/{external_id}"]
            entries: dict = nomad_json.get("entries")
            block_index = full_path_without_suffix.as_posix().rfind("block")
            nomad_name = (Path(upload_preparation_dir.name) / Path(
                (full_path_without_suffix.as_posix()[block_index:])) / vasp_run_name).as_posix()
            first_launcher_index = full_path_without_suffix.as_posix().find("launcher")
            # nomad_name = (upload_preparation_dir.name /
            #               Path(full_path_without_suffix.as_posix()[last_launcher_index:]) / vasp_run_name).as_posix()
            entries[nomad_name] = {"external_id": external_id, "references": references}
            # last_launcher_index = full_file_path.as_posix().rfind("launcher")
            untar_source_file_path_to_arcname_map.append(
                (full_file_path.as_posix(), full_file_path.as_posix()[block_index:first_launcher_index - 1]))
    return nomad_json, untar_source_file_path_to_arcname_map


def write_zip_from_targz(untar_source_file_path_to_arcname_map, upload_preparation_dir: Path, name) -> str:
    """

    1. unzip the source_file_path (which is pointing to a .zip file) using  the arcname to the upload_prearation_dir
    2. tar.gz  the entire upload_preparation_dir
    :param untar_source_file_path_to_arcname_map: file_path -> arcname mapping
    :param upload_preparation_dir: directoryt o unzip and tar.gz files
    :param name: name of the thread used

    :return:
        zip the entire upload_preparation_dir
    """
    logger.info(f"[{name}] Extracting Files")
    for full_file_path, block_name in tqdm(untar_source_file_path_to_arcname_map):
        tar = tarfile.open(full_file_path, "r:gz")
        tar.extractall(path=upload_preparation_dir / block_name)
        tar.close()

    # zip the file
    zipped_upload_preparation_file_path = upload_preparation_dir.as_posix() + ".zip"
    logger.info(f"[{name}] Zipping files to [{zipped_upload_preparation_file_path}] (This may take a while)")
    zipf = ZipFile(zipped_upload_preparation_file_path, 'w', ZIP_DEFLATED)
    zipdir(upload_preparation_dir.as_posix(), zipf)
    zipf.write(filename=upload_preparation_dir / "nomad.json", arcname="nomad.json")
    zipf.close()
    return zipped_upload_preparation_file_path


def zipdir(path, ziph):
    # ziph is zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file),
                       os.path.relpath(os.path.join(root, file),
                                       os.path.join(path, '..')))


def write_json(upload_preparation_dir, nomad_json, name):
    # json_file_name = f"nomad_{datetime.now().strftime('%m_%d_%Y_%H_%M_%S')}.json"
    json_file_name = "nomad.json"
    json_file_path = upload_preparation_dir / json_file_name
    with open(json_file_path.as_posix(), 'w') as outfile:
        json.dump(nomad_json, outfile, indent=4)
    logger.info(f"[{name}] NOMAD JSON prepared")


def md5_update_from_file(filename: Union[str, Path], hash: Hash) -> Hash:
    """
    Produce hash of the file
    :param filename: name if file to hash
    :param hash: previous hash
    :return:
        hash
    """
    assert Path(filename).is_file()
    with open(str(filename), "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash.update(chunk)
    return hash


def md5_file(filename: Union[str, Path]) -> str:
    return str(md5_update_from_file(filename, hashlib.md5()).hexdigest())


def md5_update_from_dir(directory: Union[str, Path], hash: Hash) -> Hash:
    """
    Hash directory
    :param directory: directory to hash
    :param hash: previous hash
    :return:
        hash
    """
    assert Path(directory).is_dir()
    for path in sorted(Path(directory).iterdir(), key=lambda p: str(p).lower()):
        hash.update(path.name.encode())
        if path.is_file():
            hash = md5_update_from_file(path, hash)
        elif path.is_dir():
            hash = md5_update_from_dir(path, hash)
    return hash


def md5_dir(directory: Union[str, Path]) -> str:
    """
    :param directory: directory to compute md5 hash on
    :return:
        the hash in string
    """
    return str(md5_update_from_dir(directory, hashlib.md5()).hexdigest())


def fill_record_data(record: GDriveLog, raw_dir: Path, compress_dir: Path):
    compress_file_dir = (compress_dir / record.path).as_posix() + ".tar.gz"
    record.file_size = os.path.getsize(compress_file_dir)
    record.md5hash = md5_dir(raw_dir / record.path)
    list_of_files = getListOfFiles(dirName=(raw_dir / record.path).as_posix())
    record.files.extend([_make_file_dict(file_path=Path(file), start_at=record.path) for file in list_of_files])


def getListOfFiles(dirName):
    """
        For the given path, get the List of all files in the directory tree
    """
    listOfFile = os.listdir(dirName)
    allFiles = list()
    for entry in listOfFile:
        fullPath = os.path.join(dirName, entry)
        if os.path.isdir(fullPath):
            allFiles = allFiles + getListOfFiles(fullPath)
        else:
            allFiles.append(fullPath)
    return allFiles


def _make_file_dict(file_path: Path, start_at: str) -> dict:
    start_index = file_path.as_posix().find(start_at) + len(start_at) + 1  # there is a slash after that
    path = file_path.as_posix()[start_index:]
    return {"path": path,
            "size": os.path.getsize(file_path.as_posix()),
            "md5hash": md5_file(file_path)}


def find_all_launcher_paths(input_dir: Path) -> List[str]:
    paths: List[str] = []
    for root, dirs, files in os.walk(input_dir.as_posix()):
        for name in dirs:
            if "launcher" in name:
                sub_paths = find_all_launcher_paths_helper(Path(root) / name)
                paths.extend(sub_paths)
    return paths


def find_all_launcher_paths_helper(input_dir: Path) -> List[str]:
    dir_name = input_dir.as_posix()
    start = dir_name.find("block_")
    dir_name = dir_name[start:]

    paths: List[str] = [dir_name]  # since itself is a launcher path
    for root, dirs, files in os.walk(input_dir.as_posix()):
        for name in dirs:
            if "launcher" in name:
                sub_paths = find_all_launcher_paths_helper(Path(root) / name)
                paths.extend(sub_paths)
    return paths


# an authenticator for NOMAD's keycloak user management
class KeycloakAuthenticator(Authenticator):
    def __init__(self, user, password, nomad_url):
        super().__init__(host=urlparse(nomad_url).netloc)
        self.user = user
        self.password = password
        self.token = None
        self.__oidc = KeycloakOpenID(
            server_url='https://nomad-lab.eu/fairdi/keycloak/auth/',
            realm_name='fairdi_nomad_prod',
            client_id='nomad_public')

    def apply(self, request):
        if self.token is None:
            self.token = self.__oidc.token(username=self.user, password=self.password)
            self.token['time'] = time.time()
        elif self.token['expires_in'] < int(time.time()) - self.token['time'] + 10:
            try:
                self.token = self.__oidc.refresh_token(self.token['refresh_token'])
                self.token['time'] = time.time()
            except Exception:
                self.token = self.__oidc.token(username=self.user, password=self.password)
                self.token['time'] = time.time()

        request.headers.setdefault('Authorization', 'Bearer %s' % self.token['access_token'])

        return request


def find_unuploaded_launcher_paths(outputfile, configfile, num) -> List[GDriveLog]:
    """
    Find launcher paths that has not been uploaded
    Prioritize for blessed tasks and recent materials

    :param outputfile: outputfile to write the launcher paths to
    :param configfile: config file for mongodb
    :param num: maximum number of materials to consider in this run
    :return:
        Success
    """
    outputfile: Path = Path(outputfile)
    configfile: Path = Path(configfile)
    if configfile.exists() is False:
        raise FileNotFoundError(f"Config file [{configfile}] is not found")

    # connect to mongo necessary mongo stores
    gdrive_mongo_store = MongograntStore(mongogrant_spec="rw:knowhere.lbl.gov/mp_core_mwu",
                                         collection_name="gdrive",
                                         mgclient_config_path=configfile.as_posix())
    material_mongo_store = MongograntStore(mongogrant_spec="ro:mongodb04.nersc.gov/mp_emmet_prod",
                                           collection_name="materials_2020_09_08",
                                           mgclient_config_path=configfile.as_posix())
    tasks_mongo_store = MongograntStore(mongogrant_spec="ro:mongodb04.nersc.gov/mp_emmet_prod",
                                        collection_name="tasks",
                                        mgclient_config_path=configfile.as_posix())
    gdrive_mongo_store.connect()
    material_mongo_store.connect()
    tasks_mongo_store.connect()
    logger.info("gdrive, material, and tasks mongo store successfully connected")

    # find un-uploaded materials task ids
    task_ids: List[str] = find_un_uploaded_materials_task_id(gdrive_mongo_store, material_mongo_store, max_num=num)
    logger.info(f"Found [{len(task_ids)}] task_ids for [{num}] materials")
    logger.info(f"Task_ids = {task_ids}")
    if outputfile.exists():
        logger.info(f"Will be over writing {outputfile}")
    else:
        logger.info(f"[{outputfile}] does not exist, creating...")
        outputfile.parent.mkdir(exist_ok=True, parents=True)
    # find launcher paths
    task_records = list(tasks_mongo_store.query(criteria={"task_id": {"$in": task_ids}},
                                                properties={"task_id": 1, "dir_name": 1}))
    gdrive_logs: List[GDriveLog] = []
    logger.info(f"Writing [{len(task_records)}] launcher paths to [{outputfile.as_posix()}]")
    output_file_stream = outputfile.open('w')
    for task in task_records:
        dir_name: str = task["dir_name"]
        start = dir_name.find("block_")
        dir_name = dir_name[start:]
        gdrive_logs.append(GDriveLog(path=dir_name, task_id=task["task_id"]))
        line = dir_name + "\n"
        output_file_stream.write(line)

    # epilogue
    output_file_stream.close()
    gdrive_mongo_store.close()
    material_mongo_store.close()
    tasks_mongo_store.close()
    return gdrive_logs


def log_to_mongodb(mongo_configfile: str, task_records: List[GDriveLog], raw_dir: Path, compress_dir: Path):
    """
    log task_records to mongodb. Filling in hash information each record

    :param mongo_configfile: mongo connection file location
    :param task_records: task_records to upload
    :param raw_dir: raw_directory
    :param compress_dir: compressed file directory
    :return:
    """
    configfile: Path = Path(mongo_configfile)
    gdrive_mongo_store = MongograntStore(mongogrant_spec="rw:knowhere.lbl.gov/mp_core_mwu",
                                         collection_name="gdrive",
                                         mgclient_config_path=configfile.as_posix())
    gdrive_mongo_store.connect()
    logger.info(f"Updating/adding {len(task_records)} launchers")
    for record in tqdm(task_records):
        # logger.info(f"Updating/adding record {record.path}")
        try:
            fill_record_data(record, raw_dir, compress_dir)
        except Exception as e:
            logger.error(f"Something weird happened: {e}.")
            record.error = e.__str__()

    gdrive_mongo_store.update(docs=[record.dict() for record in task_records], key="path")
    logger.info(f"[{gdrive_mongo_store.collection_name}] Collection Updated")
