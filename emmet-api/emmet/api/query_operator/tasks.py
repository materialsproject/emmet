"""Define common task query functionality."""

from fastapi import Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class MultiTaskIDQuery(QueryOperator):
    """Method to generate a query for different task_ids."""

    def __init__(self, use_plural: bool = True) -> None:
        """Set up a multi task ID query operator.

        Args:
            use_plural (bool) : Whether to use the plural `task_ids` when
                querying (True, default), or the singular `task_id` (False)
        """
        self.use_plural = use_plural

    def query(
        self,
        task_ids: str | None = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if task_ids:
            task_key = "task_id" + ("s" if self.use_plural else "")
            if (
                len(task_ids := [task_id.strip() for task_id in task_ids.split(",")])
                == 1
            ):
                crit[task_key] = task_ids[0]
            else:
                crit[task_key] = {"$in": task_ids}

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("task_ids", False)]
