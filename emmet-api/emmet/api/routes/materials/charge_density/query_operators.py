from fastapi import Query

from emmet.api.query_operator.core import MultiTaskIDQuery
from emmet.api.utils import STORE_PARAMS


class ChgcarTaskIDQuery(MultiTaskIDQuery):
    """
    Method to generate a query on CHGCAR metadata with calculation (task) ID
    """

    def query(
        self,
        task_ids: str = Query(
            None,
            description="Comma-separated list of calculation (task) IDs to query on",
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(task_ids)
