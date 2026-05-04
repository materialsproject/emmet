"""Define common task query functionality."""

from fastapi import Query
from dataclasses import dataclass
from typing import Any
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS, process_identifiers


@dataclass
class MultiTaskIDQuery(QueryOperator):
    """Generate a query for different task_ids.

    Args:
    key (bool) : Key to query on, defaults to `task_id`
    validate (bool) : Whether to ensure the identifiers are valid AlphaIDs
    use_prefix (bool) : Whether to strip prefixes when validating IDs.
        Only applies if validate is True
    store_ids (bool) : Whether to store the identifiers for post-processing
    """

    key: str = "task_id"
    validate: bool = False
    use_prefix: bool = False
    store_ids: bool = False

    def __post_init__(self) -> None:
        """Allow for accessing IDs for post-processing."""
        self.task_ids: list[str] | None = None

    def query(
        self,
        task_ids: str | None = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit: dict[str, Any] = {}

        if task_ids:
            if self.validate:
                parsed_task_ids = process_identifiers(
                    task_ids, use_prefix=self.use_prefix
                )
            else:
                parsed_task_ids = [task_id.strip() for task_id in task_ids.split(",")]

            self.task_ids = parsed_task_ids if self.store_ids else None

            crit[self.key] = (
                parsed_task_ids[0]
                if len(parsed_task_ids) == 1
                else {"$in": parsed_task_ids}
            )

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [(self.key, False)]
