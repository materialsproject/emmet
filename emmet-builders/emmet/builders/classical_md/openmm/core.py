import warnings
from typing import Optional, List
from tempfile import TemporaryDirectory
from pathlib import Path

import numpy as np

from maggma.core import Builder, Store
from openff.interchange import Interchange
from emmet.core.classical_md.openmm import OpenMMTaskDocument
from emmet.builders.classical_md.utils import create_universe


class OpenMMBuilder(Builder):
    def __init__(
        self,
        md_docs: Store,
        blobs: Store,
        solute: Store,
        query: Optional[dict] = None,
        chunk_size: int = 10,
    ):
        self.md_docs = md_docs
        self.blobs = blobs
        self.solute = solute

        self.query = query or {}

        if self.md_docs.key != "uuid":
            warnings.warn(
                "Key for the corrected entries store is incorrect and has been changed "
                f"from {self.md_docs.key} to uuid!"
            )
            self.md_docs.key = "uuid"

        if self.blobs.key != "blob_uuid":
            warnings.warn(
                "Key for the blobs store is incorrect and has been changed "
                f"from {self.blobs.key} to blob_uuid!"
            )
            self.blobs.key = "blob_uuid"

        super().__init__(
            sources=[md_docs, blobs], targets=[solute], chunk_size=chunk_size
        )

    # def prechunk(self, number_splits: int):  # pragma: no cover
    #     """
    #     Prechunk method to perform chunking by the key field
    #     """
    #     q = dict(self.query)
    #
    #     keys = self.electronic_structure.newer_in(
    #         self.materials, criteria=q, exhaustive=True
    #     )
    #
    #     N = ceil(len(keys) / number_splits)
    #     for split in grouper(keys, N):
    #         yield {"query": {self.materials.key: {"$in": list(split)}}}

    def process_items(self, items):
        for item in items:
            # create task_doc
            task_doc = OpenMMTaskDocument.parse_obj(item["output"])
            # create interchange
            interchange_str = task_doc.interchange.decode("utf-8")
            interchange = Interchange.parse_raw(interchange_str)
            # create temporary directory
            with TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                calc_output = task_doc.calcs_reversed[0].output
                # write trajectory to file
                with open(temp_path / calc_output.traj_file, "wb") as f:
                    f.write(calc_output.traj_blob)
                create_universe(
                    interchange,
                    task_doc.molecule_specs,
                    temp_path / calc_output.traj_file,
                )
                # identify_solute(u, task_doc)
                # identify_networking_solvents(u, task_doc)
                # TODO: fix hardcode
                # create_solute(u, solute_name="O", networking_solvents=["O"])
                # solute.run()
                #
                # doc = SolvationDoc.from_solute(solute)

    def get_items(self):
        hosts = self.md_docs.query(self.query, ["hosts"])
        flow_ids = {doc["hosts"][-1] for doc in hosts}  # top level flows

        job_groups = []
        for flow_id in flow_ids:
            mg_filter = {"$expr": {"$eq": [{"$arrayElemAt": ["$hosts", -1]}, flow_id]}}
            job_groups.append(list(self.md_docs.query(criteria=mg_filter)))

        items = []
        for jobs in job_groups:
            # TODO: check for changes in non_calc features
            # TODO: support branching flows

            # find the job with the most calcs in the flow, presumably the last
            jobs = job_groups[0]
            len_calcs = [len(job["output"]["calcs_reversed"] or []) for job in jobs]
            last_job = jobs[np.argmax(len_calcs)]

            # inject interchange blobs
            interchange_uuid = last_job["output"]["interchange"]["blob_uuid"]
            interchange_blob = self.blobs.query_one({"blob_uuid": interchange_uuid})
            last_job["output"]["interchange"] = interchange_blob["data"]

            for calc in last_job["output"]["calcs_reversed"]:
                traj_blob = calc["output"]["traj_blob"]
                # inject trajectory blobs
                if traj_blob:
                    traj_uuid = calc["output"]["traj_blob"]["blob_uuid"]
                    traj_blob = self.blobs.query_one({"blob_uuid": traj_uuid})
                    calc["output"]["traj_blob"] = traj_blob["data"]

            items.append(last_job)

        return items

    def update_targets(self, items: List):
        return
