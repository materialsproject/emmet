from collections import deque

from maggma.builders import Builder


class StructureStatus(Builder):
    def __init__(self, wflow_logs, status, **kwargs):
        super().__init__(
            sources=[status, wflow_logs],
            target=[status],
            **kwargs
        )

    def get_items(self):
        status, wflow_logs = self.sources
        snl_ids = status.distinct("snl_id", {"state": {"$in": ["SUBMITTED", "RUNNING"]}})
        criteria = {"snl_id": {"$in": snl_ids}}
        projection = ["level", "canonical_snl_id", "fw_id", "task_id", "task_id(s)"]
        docs = wflow_logs.query(criteria, projection)
        queue = deque(docs)
        while len(queue):
            doc = queue.popleft()
            if doc.get("canonical_snl_id"):
                queue.append(wflow_logs.query_one({"snl_id": doc["canonical_snl_id"]}, projection))
            elif doc["level"] == "ERROR":
                yield ("error", doc)
            elif doc.get("fw_id"):
                doc.update(self.get_fw_status(doc["fw_id"]))
                yield ("running", doc)
            elif doc.get("task_id") or doc.get("task_id(s)"):
                doc.update(self.get_task_info(doc))
                yield ("completed", doc)

    @classmethod
    def get_fw_status(cls, fw_id):
        raise NotImplementedError

    @classmethod
    def get_task_info(cls, doc):
        raise NotImplementedError

    def process_item(self, item):
        raise NotImplementedError

    def update_targets(self, items):
        raise NotImplementedError
