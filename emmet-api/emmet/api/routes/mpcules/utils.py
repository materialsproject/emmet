from typing import Optional

from fastapi import Query

from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class MethodQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        calculation method.
    """

    def query(
        self,
        method: Optional[str] = Query(
            None,
            description="Query by calculation method (e.g. mulliken, nbo).",
        ),
    ) -> STORE_PARAMS:

        crit = {}

        if method:
            crit.update({"method": method.lower()})

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("method", False)]
