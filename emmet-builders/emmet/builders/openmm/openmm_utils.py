from typing import Union
from pathlib import Path

from openff.interchange import Interchange
from maggma.core import Store

from emmet.core.openmm import OpenMMTaskDocument, OpenMMInterchange
from emmet.builders.openmm.utils import create_universe

import tempfile


def insert_blobs(blobs_store: Store, task_doc: dict, include_traj: bool = True):
    """Insert blobs into a task document."""
    interchange_uuid = task_doc["interchange"]["blob_uuid"]
    interchange_blob = blobs_store.query_one({"blob_uuid": interchange_uuid})
    task_doc["interchange"] = interchange_blob["data"]

    if len(task_doc["calcs_reversed"]) == 0:
        raise ValueError("No calculations found in job output.")

    for calc in task_doc["calcs_reversed"]:
        if not include_traj:
            calc["output"]["traj_blob"] = None

        traj_blob = calc["output"]["traj_blob"]

        if traj_blob:
            traj_uuid = calc["output"]["traj_blob"]["blob_uuid"]
            traj_blob = blobs_store.query_one({"blob_uuid": traj_uuid})
            calc["output"]["traj_blob"] = traj_blob["data"]


def instantiate_universe(
    md_docs: Store,
    blobs: Store,
    job_uuid: str,
    traj_directory: Union[str, Path] = ".",
    overwrite_local_traj: bool = True,
):
    """
    Instantiate a MDAnalysis universe from a task document.

    This is useful if you want to analyze a small number of systems
    without running the whole build pipeline.

    Args:
        md_docs: Store
            The store containing the task documents.
        blobs: Store
            The store containing the blobs.
        job_uuid: str
            The UUID of the job.
        traj_directory: str
            Name of the DCD file to write.
        overwrite_local_traj: bool
            Whether to overwrite the local trajectory if it exists.
    """

    # pull job
    docs = list(md_docs.query(criteria={"uuid": job_uuid}))
    if len(docs) != 1:
        raise ValueError(
            f"The job_uuid, {job_uuid}, must be unique. Found {len(docs)} documents."
        )
    task_doc = docs[0]["output"]
    traj_file_type = task_doc["calcs_reversed"][0]["input"]["traj_file_type"]

    # define path to trajectory
    traj_directory = Path(traj_directory)
    traj_directory.mkdir(parents=True, exist_ok=True)
    traj_path = traj_directory / f"{job_uuid}.{traj_file_type}"

    # download and insert blobs if necessary
    new_traj = not traj_path.exists() or overwrite_local_traj
    insert_blobs(blobs, task_doc, include_traj=new_traj)
    task_doc = OpenMMTaskDocument.parse_obj(task_doc)
    if new_traj:
        with open(traj_path, "wb") as f:
            f.write(task_doc.calcs_reversed[0].output.traj_blob)

    # create interchange
    interchange_str = task_doc.interchange.decode("utf-8")
    interchange = Interchange.parse_raw(interchange_str)

    return create_universe(
        interchange,
        task_doc.molecule_specs,
        traj_path,
        traj_format=traj_file_type,
    )


def resolve_traj_path(task_doc, local_trajectories, rebase_traj_path):
    calc = task_doc.calcs_reversed[0]

    if local_trajectories:
        traj_file = calc.output.traj_file
        traj_path = Path(calc.output.dir_name) / traj_file
        if rebase_traj_path:
            old, new = rebase_traj_path
            traj_path = new / traj_path.relative_to(old)
    else:
        traj_file = tempfile.NamedTemporaryFile()
        traj_path = Path(traj_file.name)
        with open(traj_path, "wb") as f:
            f.write(calc.output.traj_blob)
    return traj_path, traj_file


def task_doc_to_universe(task_doc, traj_path):
    calc = task_doc.calcs_reversed[0]

    # create interchange
    interchange_str = task_doc.interchange.decode("utf-8")
    try:
        interchange = Interchange.parse_raw(interchange_str)
    except:  # noqa: E722
        # parse with openmm instead
        interchange = OpenMMInterchange.parse_raw(interchange_str)

    return create_universe(
        interchange,
        task_doc.molecule_specs,
        traj_path,
        traj_format=calc.input.traj_file_type,
    )
