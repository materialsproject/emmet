import warnings
from typing import Optional, List
from pathlib import Path
import tempfile

import numpy as np

from maggma.core import Builder, Store
from openff.interchange import Interchange
from emmet.core.classical_md.openmm import OpenMMTaskDocument
from emmet.builders.classical_md.utils import (
    create_universe,
    create_solute,
    identify_solute,
    identify_networking_solvents,
)
from emmet.core.classical_md.solvation import SolvationDoc
from emmet.core.utils import jsanitize


class ElectrolyteBuilder(Builder):
    def __init__(
        self,
        md_docs: Store,
        blobs: Store,
        solute: Store,
        query: Optional[dict] = None,
        solvation_fallback_radius: float = 3,
        chunk_size: int = 10,
    ):
        self.md_docs = md_docs
        self.blobs = blobs
        self.solute = solute
        self.query = query or {}
        self.solvation_fallback_radius = solvation_fallback_radius

        # TODO: needed?
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

        if self.solute.key != "job_uuid":
            warnings.warn(
                "Key for the solute store is incorrect and has been changed "
                f"from {self.solute.key} to job_uuid!"
            )
            self.solute.key = "job_uuid"

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

    def get_items(self):
        self.logger.info("Electrolyte builder started.")

        hosts = self.md_docs.query(self.query, ["hosts"])
        flow_ids = {doc["hosts"][-1] for doc in hosts}  # top level flows

        job_groups = []
        for flow_id in flow_ids:
            # get last item in hosts, which should be top level workflow
            mg_filter = {"$expr": {"$eq": [{"$arrayElemAt": ["$hosts", -1]}, flow_id]}}
            job_groups.append(list(self.md_docs.query(criteria=mg_filter)))

        items = []
        for jobs in job_groups:
            # TODO: check for changes in non_calc features
            # TODO: support branching flows

            # find the job with the most calcs in the flow, presumably the last
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

    def process_items(self, items):
        self.logger.info(f"Processing {len(items)} materials for electrolyte builder.")

        processed_items = []
        for item in items:
            # create task_doc
            task_doc = OpenMMTaskDocument.parse_obj(item["output"])
            calc = task_doc.calcs_reversed[0]

            # create interchange
            interchange_str = task_doc.interchange.decode("utf-8")
            interchange = Interchange.parse_raw(interchange_str)

            # write the trajectory to a file
            traj_file = tempfile.NamedTemporaryFile()
            traj_path = Path(traj_file.name)
            with open(traj_path, "wb") as f:
                f.write(calc.output.traj_blob)
            u = create_universe(
                interchange,
                task_doc.molecule_specs,
                traj_path,
                traj_format=calc.input.traj_file_type,
            )

            # create solute_doc
            solute = create_solute(
                u,
                solute_name=identify_solute(u),
                networking_solvents=identify_networking_solvents(u),
                fallback_radius=self.solvation_fallback_radius,
            )
            solute.run()
            solvation_doc = SolvationDoc.from_solute(solute, job_uuid=item["uuid"])

            # create docs
            # TODO: what cleanup do I need?
            docs = {
                "solute": jsanitize(solvation_doc.model_dump()),
            }

            processed_items.append(docs)

        return processed_items

    def update_targets(self, items: List):
        if len(items) > 0:
            self.logger.info(f"Found {len(items)} electrolyte docs to update.")
            solutes = [item["solute"] for item in items]
            self.solute.update(solutes)
        else:
            self.logger.info("No items to update.")
