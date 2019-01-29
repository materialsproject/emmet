from collections import deque

from maggma.builders import Builder


class StructureStatus(Builder):
    def __init__(self, wflow_logs, wflows, status, **kwargs):
        super().__init__(
            sources=[status, wflow_logs, wflows],
            target=[status],
            **kwargs
        )

    def get_items(self):
        # NOTE if not already done, SNL should first be checked against publicly released materials
        status, wflow_logs, wflows = self.sources
        snl_ids = status.distinct("snl_id", {"state": {"$in": ["SUBMITTED", "RUNNING"]}})
        criteria = {"snl_id": {"$in": snl_ids}}
        projection = ["level", "message", "canonical_snl_id", "fw_id", "task_id", "task_id(s)"]
        docs = wflow_logs.query(criteria, projection)
        queue = deque(docs)
        while len(queue):
            doc = queue.popleft()
            if doc.get("canonical_snl_id"):
                queue.append(wflow_logs.query_one({"snl_id": doc["canonical_snl_id"]}, projection))
            elif doc["level"] == "ERROR":
                yield ("error", doc) # NOTE see doc["message"] for error details
            elif doc.get("fw_id"):
                doc.update(wflows.query_one({"nodes": doc["fw_id"]}, {"_id": 0, "state": 1}))
                if doc["state"] == "COMPLETED":
                    yield ("release-ready", doc)
                else:
                    yield ("running", doc)
            elif doc.get("task_id") or doc.get("task_id(s)"):
                # NOTE nothing to do here other than mark as "RELEASE-READY"
                yield ("release-ready", doc)

    def process_item(self, item):
        raise NotImplementedError

    def update_targets(self, items):
        raise NotImplementedError
