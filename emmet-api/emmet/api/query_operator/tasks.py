"""Define common task query functionality."""

from fastapi import Query
from typing import Any
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS, process_identifiers


class MultiTaskIDQuery(QueryOperator):
    """Method to generate a query for different task_ids."""

    def __init__(self, use_plural: bool = True, validate: bool = False) -> None:
        """Set up a multi task ID query operator.

        Args:
            use_plural (bool) : Whether to use the plural `task_ids` when
                querying (True, default), or the singular `task_id` (False)
            validate (bool) : Whether to ensure the identifiers are valid AlphaIDs
        """
        self.use_plural = use_plural
        self.validate = validate

    def query(
        self,
        task_ids: str | None = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit: dict[str, Any] = {}

        if task_ids:
            task_key = "task_id" + ("s" if self.use_plural else "")
            if self.validate:
                parsed_task_ids = process_identifiers(task_ids, use_prefix=False)
            else:
                parsed_task_ids = [task_id.strip() for task_id in task_ids.split(",")]

            crit[task_key] = (
                parsed_task_ids[0]
                if len(parsed_task_ids) == 1
                else {"$in": parsed_task_ids}
            )

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("task_ids", False)]
