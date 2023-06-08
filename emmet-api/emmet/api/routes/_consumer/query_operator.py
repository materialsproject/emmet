from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Body, Query
from maggma.api.query_operator import QueryOperator

if TYPE_CHECKING:
    from maggma.api.utils import STORE_PARAMS


class UserSettingsPostQuery(QueryOperator):
    """Query operators to provide user settings information to post."""

    def query(
        self,
        consumer_id: str = Query(
            ...,
            title="Consumer ID",
        ),
        settings: dict = Body(
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


class UserSettingsGetQuery(QueryOperator):
    """Query operators to provide user settings information."""

    def query(
        self,
        consumer_id: str = Query(
            ...,
            title="Consumer ID",
        ),
    ) -> STORE_PARAMS:
        crit = {"consumer_id": consumer_id}

        return {"criteria": crit}
