from datetime import datetime
from typing import Dict, Optional
from fastapi import Query, Body
from maggma.api.utils import STORE_PARAMS
from maggma.api.query_operator import QueryOperator


class UserSettingsPostQuery(QueryOperator):
    """Query operators to provide user settings information to post"""

    def query(
        self,
        consumer_id: str = Query(
            ...,
            title="Consumer ID",
        ),
        settings: Dict = Body(
            ...,
            title="User settings",
        ),
    ) -> STORE_PARAMS:
        crit = {"consumer_id": consumer_id, "settings": settings}

        return {"criteria": crit}

    def post_process(self, docs, query):
        cid = query["criteria"]["consumer_id"]
        settings = query["criteria"]["settings"]

        d = [{"consumer_id": cid, "settings": settings}]

        return d


class UserSettingsPatchQuery(QueryOperator):
    """Query operators to provide user settings information to potch"""

    def query(
        self,
        consumer_id: str = Query(
            ...,
            title="Consumer ID",
        ),
        fields_to_update: Optional[Dict] = Body(
            None, title="Field name and value to update in user settings"
        ),
    ) -> STORE_PARAMS:
        crit = {"consumer_id": consumer_id}

        if fields_to_update and "settings.message_last_read" in fields_to_update:
            # Parse the ISO-formatted timestamp string into a datetime object
            time = datetime.fromisoformat(
                fields_to_update["settings.message_last_read"]
            )
            fields_to_update["settings.message_last_read"] = time

        return (
            dict(criteria=crit, update=fields_to_update)
            if fields_to_update
            else dict(criteria=crit)
        )


class UserSettingsGetQuery(QueryOperator):
    """Query operators to provide user settings information"""

    def query(
        self,
        consumer_id: str = Query(
            ...,
            title="Consumer ID",
        ),
    ) -> STORE_PARAMS:
        crit = {"consumer_id": consumer_id}

        return {"criteria": crit}
