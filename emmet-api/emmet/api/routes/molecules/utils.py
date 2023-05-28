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


class MultiPropertyIDQuery(QueryOperator):
    """
    Method to generate a query for different property ID values
    """

    def query(
        self,
        property_ids: Optional[str] = Query(
            None, description="Comma-separated list of property_id values to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if property_ids:
            property_id_list = [pid.strip() for pid in property_ids.split(",")]

            if len(property_id_list) == 1:
                crit.update({"property_id": property_id_list[0]})
            else:
                crit.update({"property_id": {"$in": property_id_list}})

        return {"criteria": crit}
