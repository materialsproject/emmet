from datetime import datetime
from typing import Optional

from fastapi import Query

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class SubmissionQuery(QueryOperator):
    """
    Method to generate a query for submission data using status and datetime.
    """

    def __init__(self, status_enum):
        self.status_enum = status_enum

        def query(
            state: Optional[status_enum] = Query(
                None, description="Latest status of the submission"
            ),
            last_updated: Optional[datetime] = Query(
                None,
                description="Minimum datetime of status update for submission",
            ),
        ) -> STORE_PARAMS:
            crit = {}  # type: dict

            if state:
                s_dict = {"$expr": {"$eq": [{"$arrayElemAt": ["$state", -1]}, state.value]}}  # type: ignore
                crit.update(s_dict)

            if last_updated:
                l_dict = {
                    "$expr": {
                        "$gt": [{"$arrayElemAt": ["$last_updated", -1]}, last_updated]
                    }
                }
                crit.update(l_dict)

            if state and last_updated:
                crit = {"$and": [s_dict, l_dict]}

            return {"criteria": crit}

        self.query = query

    def query(self):
        """Stub query function for abstract class."""
