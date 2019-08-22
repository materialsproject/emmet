from datetime import datetime
from collections import deque

from maggma.builders import Builder
from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymongo import UpdateOne

from emmet.magic_numbers import LTOL, STOL, ANGLE_TOL

class StructureWorkflowStatus(Builder):
    def __init__(self, jobs_src, wflow_logs, wflows, jobs_tgt, **kwargs):
        self.jobs_src = jobs_src
        self.wflow_logs = wflow_logs
        self.wflows = wflows
        self.jobs_tgt = jobs_tgt
        self.kwargs = kwargs
        self.total = None
        super().__init__(
            sources=[jobs_src, wflow_logs, wflows],
            targets=[jobs_tgt],
            **kwargs
        )

    def get_items(self):
        # NOTE if not already done, SNL should first be checked against publicly released materials
        jobs, wflow_logs, wflows = self.sources
        snl_ids = jobs.distinct("snl_id", {"wflow.status": {"$nin": ["error", "release-ready", "released"]}})
        criteria = {"snl_id": {"$in": snl_ids}}
        projection = ["snl_id", "level", "message", "canonical_snl_id", "fw_id", "task_id", "task_id(s)"]
        docs = list(wflow_logs.query(criteria, projection))
        self.total = len(docs)
        queue = deque(docs)
        while len(queue):
            doc = queue.popleft()
            if doc.get("canonical_snl_id"):
                job_snl_id = doc["snl_id"]
                doc = wflow_logs.query_one({"snl_id": doc["canonical_snl_id"]}, projection)
                doc.update({"snl_id": job_snl_id})
                queue.append(doc)
            elif doc["level"] == "ERROR":
                yield ("error", doc) # NOTE see doc["message"] for error details
            elif doc.get("fw_id"):
                doc.update(wflows.query_one({"nodes": doc["fw_id"]}, {"_id": 0, "state": 1}))
                if doc["state"] == "COMPLETED":
                    yield ("release-ready", doc)
                elif doc["state"] in ("ARCHIVED", "FIZZLED", "PAUSED", "DEFUSED"):
                    yield ("error", doc)
                else:
                    yield ("running", doc)
            elif doc.get("task_id") or doc.get("task_id(s)"):
                yield ("release-ready", doc)
            else:
                yield ("uh-oh", doc)

    def process_item(self, item):
        status_msg, doc = item
        out = doc.copy()
        out.pop("_id")
        out.update(status=status_msg)
        return out

    def update_targets(self, items):
        jobs = self.targets[0]
        key, now = jobs.key, datetime.utcnow()
        for d in items:
            d[jobs.lu_field] = now
        requests = [UpdateOne({key: d[key]}, {"$set": {"wflow": d}}) for d in items]
        if requests:
            jobs.collection.bulk_write(requests, ordered=False)


class StructureReleaseStatus(Builder):
    def __init__(self, materials, jobs_src, jobs_tgt, **kwargs):
        self.materials = materials
        self.jobs_src = jobs_src
        self.jobs_tgt = jobs_tgt
        self.kwargs = kwargs
        self.total = None
        super().__init__(
            sources=[materials, jobs_src],
            targets=[jobs_tgt],
            **kwargs
        )

    def get_items(self):
        materials, jobs = self.sources
        matcher = StructureMatcher(
            ltol=LTOL, stol=STOL, angle_tol=ANGLE_TOL, primitive_cell=True, scale=True,
            attempt_supercell=False, comparator=ElementComparator())
        jobs = list(jobs.query({"wflow.status": "release-ready"}))
        self.total = len(jobs)
        for job in jobs:
            structure = Structure.from_dict(job)
            criteria = {"pretty_formula": structure.composition.reduced_formula}
            material_id = next((
                r['task_id'] for r in materials.query(criteria, ['structure', 'task_id'])
                if matcher.fit(structure, Structure.from_dict(r['structure']))), None)
            if material_id:
                yield (
                    {"snl_id": job["snl_id"]},
                    {"wflow.status": "released", "wflow.material_id": material_id}
                )

    def update_targets(self, items):
        requests = []
        for (criteria, to_set) in items:
            requests.append(UpdateOne(criteria, {"$set": to_set}))
        if requests:
            self.targets[0].collection.bulk_write(requests, ordered=False)


