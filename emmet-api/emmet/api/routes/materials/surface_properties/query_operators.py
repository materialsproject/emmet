from fastapi import Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class ReconstructedQuery(QueryOperator):
    """
    Method to generate a query on whether the entry
    contains a reconstructed surface.
    """

    def query(
        self,
        has_reconstructed: bool | None = Query(
            None,
            description="Whether the entry has a reconstructed surface.",
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if has_reconstructed is not None:
            crit.update({"has_reconstructed": has_reconstructed})

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("has_reconstructed", False)]
