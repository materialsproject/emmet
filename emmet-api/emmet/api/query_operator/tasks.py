"""Define common task query functionality."""

from fastapi import Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class MultiTaskIDQuery(QueryOperator):
    """
    Method to generate a query for different task_ids
    """

    def query(
        self,
        task_ids: str | None = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if task_ids:
            crit.update(
                {
                    "task_ids": {
                        "$in": [task_id.strip() for task_id in task_ids.split(",")]
                    }
                }
            )

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("task_ids", False)]
