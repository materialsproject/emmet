from typing import Optional, List, Union
from pathlib import Path

import numpy as np

from maggma.core import Builder, Store
from maggma.stores import MemoryStore
from emmet.builders.openmm.utils import (
    create_solute,
    identify_solute,
    identify_networking_solvents,
)
from emmet.core.openff.solvation import SolvationDoc
from emmet.core.openff.benchmarking import SolventBenchmarkingDoc
from emmet.core.openmm import OpenMMTaskDocument
from emmet.core.openmm.calculations import CalculationsDoc
from emmet.core.utils import jsanitize

from emmet.builders.openmm.openmm_utils import (
    insert_blobs,
    instantiate_universe,
    resolve_traj_path,
    task_doc_to_universe,
)


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
        solute: Optional[Store] = None,
        calculations: Optional[Store] = None,
        query: Optional[dict] = None,
        solute_analysis_classes: Union[List[str], str] = "all",
        solvation_fallback_radius: float = 3,
        chunk_size: int = 10,
    ):
        self.md_docs = md_docs
        self.blobs = blobs
        self.solute = solute or MemoryStore()
        self.calculations = calculations or MemoryStore()
        self.query = query or {}
        self.solute_analysis_classes = solute_analysis_classes
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
    #     keys = self.electronic_structure.newer_in(
    #         self.materials, criteria=q, exhaustive=True
    #     )
    #     N = ceil(len(keys) / number_splits)
    #     for split in grouper(keys, N):
    #         yield {"query": {self.materials.key: {"$in": list(split)}}}

    def get_items(self, local_trajectories=False):
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
            # find the job with the most calcs in the flow, presumably the last
            len_calcs = [len(job["output"]["calcs_reversed"] or []) for job in jobs]
            last_job = jobs[np.argmax(len_calcs)]

            insert_blobs(
                self.blobs, last_job["output"], include_traj=not local_trajectories
            )

            items.append(last_job)

        return items

    def get_items_from_directories(self):
        # query will be ignored
        return

    def process_items(
        self,
        items: List,
        local_trajectories: bool = False,
        rebase_traj_path: Optional[tuple[Path, Path]] = None,
    ):
        """

        Parameters
        ----------
        items: the items from get_items
        local_trajectories: whether to look for files locally in lieu of downloading
        rebase_traj_path: useful if the launch directory has moved

        Returns
        -------

        """
        self.logger.info(f"Processing {len(items)} materials for electrolyte builder.")

        processed_items = []
        for item in items:
            # create task_doc
            task_doc = OpenMMTaskDocument.parse_obj(item["output"])

            # _ is needed bc traj_path may be a tmpfile and a reference must be in scope
            traj_path, _ = resolve_traj_path(
                task_doc, local_trajectories, rebase_traj_path
            )

            u = task_doc_to_universe(task_doc, traj_path)

            # create solute_doc
            solute = create_solute(
                u,
                solute_name=identify_solute(u),
                networking_solvents=identify_networking_solvents(u),
                fallback_radius=self.solvation_fallback_radius,
                analysis_classes=self.solute_analysis_classes,
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

    def instantiate_universe(
        self,
        job_uuid: str,
        traj_directory: Union[str, Path] = ".",
        overwrite_local_traj: bool = True,
    ):
        """
        Instantiate a MDAnalysis universe from a task document.

        This is useful if you want to analyze a small number of systems
        without running the whole build pipeline.

        To get a solute, call create_solute using the universe. See
        the body of process_items for the appropriate syntax.

        Args:
            job_uuid: str
                The UUID of the job.
            traj_directory: str
                Name of the DCD file to write.
            overwrite_local_traj: bool
                Whether to overwrite the local trajectory if it exists.
        """
        return instantiate_universe(
            self.md_docs, self.blobs, job_uuid, traj_directory, overwrite_local_traj
        )


class BenchmarkingBuilder(Builder):
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
        benchmarking: Optional[Store] = None,
        query: Optional[dict] = None,
        chunk_size: int = 10,
    ):
        self.md_docs = md_docs
        self.blobs = blobs
        self.benchmarking = benchmarking or MemoryStore()
        self.query = query or {}

        self.md_docs.key = "uuid"
        self.blobs.key = "blob_uuid"
        self.benchmarking.key = "job_uuid"

        super().__init__(
            sources=[md_docs, blobs],
            targets=[self.benchmarking],
            chunk_size=chunk_size,
        )

    # def prechunk(self, number_splits: int):  # pragma: no cover
    #     """
    #     Prechunk method to perform chunking by the key field
    #     """
    #     q = dict(self.query)
    #     keys = self.electronic_structure.newer_in(
    #         self.materials, criteria=q, exhaustive=True
    #     )
    #     N = ceil(len(keys) / number_splits)
    #     for split in grouper(keys, N):
    #         yield {"query": {self.materials.key: {"$in": list(split)}}}

    def get_items(self, local_trajectories=False):
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
            # find the job with the most calcs in the flow, presumably the last
            len_calcs = [len(job["output"]["calcs_reversed"] or []) for job in jobs]
            last_job = jobs[np.argmax(len_calcs)]

            insert_blobs(
                self.blobs, last_job["output"], include_traj=not local_trajectories
            )

            items.append(last_job)

        return items

    def get_items_from_directories(self):
        # query will be ignored
        return

    def process_items(
        self,
        items,
        local_trajectories: bool = False,
        rebase_traj_path: Optional[tuple[Path, Path]] = None,
        **benchmarking_kwargs,
    ):
        self.logger.info(f"Processing {len(items)} materials for electrolyte builder.")

        processed_items = []
        for item in items:
            # create task_doc
            task_doc = OpenMMTaskDocument.parse_obj(item["output"])

            # _tmp_file is needed bc traj_path may be a tmpfile and a
            # reference must be in scope
            traj_path, _tmp_file = resolve_traj_path(
                task_doc, local_trajectories, rebase_traj_path
            )

            u = task_doc_to_universe(task_doc, traj_path)

            benchmarking_doc = SolventBenchmarkingDoc.from_universe(
                u,
                temperature=task_doc.calcs_reversed[0].input.temperature,
                density=task_doc.calcs_reversed[0].output.density[-1],
                job_uuid=item["uuid"],
                flow_uuid=item["hosts"][-1],
                tags=task_doc.tags,
                **benchmarking_kwargs,
            )

            del u

            docs = {
                "benchmarking": jsanitize(benchmarking_doc.model_dump()),
            }

            processed_items.append(docs)

        return processed_items

    def update_targets(self, items: List):
        if len(items) > 0:
            self.logger.info(f"Found {len(items)} electrolyte docs to update.")

            calculations = [item["benchmarking"] for item in items]
            self.benchmarking.update(calculations)

        else:
            self.logger.info("No items to update.")

    def instantiate_universe(
        self,
        job_uuid: str,
        traj_directory: Union[str, Path] = ".",
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
        return instantiate_universe(
            self.md_docs, self.blobs, job_uuid, traj_directory, overwrite_local_traj
        )
