from typing import Optional, List
from pathlib import Path
import tempfile

import numpy as np

from maggma.core import Builder, Store
from maggma.stores import MemoryStore
from openff.interchange import Interchange
from emmet.core.classical_md.openmm import OpenMMTaskDocument
from emmet.builders.classical_md.utils import (
    create_universe,
    create_solute,
    identify_solute,
    identify_networking_solvents,
)
from emmet.core.classical_md.solvation import SolvationDoc
from emmet.core.classical_md.openmm.calculations import CalculationsDoc
from emmet.core.utils import jsanitize


class ElectrolyteBuilder(Builder):
    """
    Builder to create solvation and calculations documents from OpenMM task documents.

    This class processes molecular dynamics (MD) simulations and generates
    comprehensive reports including solvation properties and calculation results.
    It leverages the OpenFF toolkit and MDAnalysis for molecular topology and trajectory
    handling, respectively.
    """

    def __init__(
        self,
        md_docs: Store,
        blobs: Store,
        solute: Store | None = None,
        calculations: Store | None = None,
        query: Optional[dict] = None,
        solute_analysis_classes: List[str] | str = "all",
        solvation_fallback_radius: float = 3,
        chunk_size: int = 10,
    ):
        self.md_docs = md_docs
        self.blobs = blobs
        self.solute = solute or MemoryStore()
        self.calculations = calculations or MemoryStore()
        self.query = query or {}
        self.solvation_fallback_radius = solvation_fallback_radius

        self.md_docs.key = "uuid"
        self.blobs.key = "blob_uuid"
        if self.solute:
            self.solute.key = "job_uuid"
        if self.calculations:
            self.calculations.key = "job_uuid"

        super().__init__(
            sources=[md_docs, blobs],
            targets=[self.solute, self.calculations],
            chunk_size=chunk_size,
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
            # the last item in hosts should be the top level workflow
            host_match = {"$expr": {"$eq": [{"$arrayElemAt": ["$hosts", -1]}, flow_id]}}
            job_groups.append(list(self.md_docs.query(criteria=host_match)))

        items = []
        for jobs in job_groups:
            # TODO: check for changes in non_calc features
            # TODO: support branching flows

            # find the job with the most calcs in the flow, presumably the last
            len_calcs = [len(job["output"]["calcs_reversed"] or []) for job in jobs]
            last_job = jobs[np.argmax(len_calcs)]

            self._insert_blobs(last_job)

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
            solvation_doc = SolvationDoc.from_solute(
                solute, job_uuid=item["uuid"], flow_uuid=item["hosts"][-1]
            )
            calculations_doc = CalculationsDoc.from_calcs_reversed(
                task_doc.calcs_reversed,
                job_uuid=item["uuid"],
                flow_uuid=item["hosts"][-1],
            )

            # create docs
            # TODO: what cleanup do I need?
            docs = {
                "solute": jsanitize(solvation_doc.model_dump()),
                "calculations": jsanitize(calculations_doc.model_dump()),
            }

            processed_items.append(docs)

        return processed_items

    def update_targets(self, items: List):
        if len(items) > 0:
            self.logger.info(f"Found {len(items)} electrolyte docs to update.")

            solutes = [item["solute"] for item in items]
            self.solute.update(solutes)

            calculations = [item["calculations"] for item in items]
            self.calculations.update(calculations)

        else:
            self.logger.info("No items to update.")

    def _insert_blobs(self, job, include_traj=True):
        # inject interchange blobs
        interchange_uuid = job["output"]["interchange"]["blob_uuid"]
        interchange_blob = self.blobs.query_one({"blob_uuid": interchange_uuid})
        job["output"]["interchange"] = interchange_blob["data"]

        if len(job["output"]["calcs_reversed"]) == 0:
            raise ValueError("No calculations found in job output.")

        for calc in job["output"]["calcs_reversed"]:
            if not include_traj:
                calc["output"]["traj_blob"] = None

            traj_blob = calc["output"]["traj_blob"]

            # inject trajectory blobs
            if traj_blob:
                traj_uuid = calc["output"]["traj_blob"]["blob_uuid"]
                traj_blob = self.blobs.query_one({"blob_uuid": traj_uuid})
                calc["output"]["traj_blob"] = traj_blob["data"]

    def instantiate_universe(
        self,
        job_uuid: str,
        traj_directory: str | Path = ".",
        overwrite_local_traj: bool = True,
    ):
        """
        Instantiate a MDAnalysis universe from a task document.

        This is useful if you want to analyze a small number of systems
        without running the whole build pipeline.

        Args:
            job_uuid: str
                The UUID of the job.
            traj_directory: str
                Name of the DCD file to write.
            overwrite_local_traj: bool
                Whether to overwrite the local trajectory if it exists.
        """

        # pull job
        doc = list(self.md_docs.query(criteria={"uuid": job_uuid}))
        if len(doc) != 1:
            raise ValueError(
                f"The job_uuid, {job_uuid}, must be unique. Found {len(doc)} documents."
            )
        doc = doc[0]
        traj_file_type = doc["output"]["calcs_reversed"][0]["input"]["traj_file_type"]

        # define path to trajectory
        traj_directory = Path(traj_directory)
        traj_directory.mkdir(parents=True, exist_ok=True)
        traj_path = traj_directory / f"{job_uuid}.{traj_file_type}"

        # download and insert blobs if necessary
        new_traj = not traj_path.exists() or overwrite_local_traj
        self._insert_blobs(doc, include_traj=new_traj)
        task_doc = OpenMMTaskDocument.parse_obj(doc["output"])
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
