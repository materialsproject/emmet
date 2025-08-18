from datetime import datetime

from fastapi import Body, Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS

from emmet.core._messages import MessageType


class MessagesPostQuery(QueryOperator):
    """Query operators to provide message information to post"""

    def query(
        self,
        title: str = Body(
            ...,
            title="Message title",
        ),
        body: str = Body(
            ...,
            title="Message text body",
        ),
        authors: list[str] = Body(
            [],
            title="Message authors",
        ),
        type: MessageType = Body(
            "generic",
            title="Message type",
        ),
        last_updated: datetime = Body(
            datetime.utcnow(),
            title="Message last update datetime",
        ),
    ) -> STORE_PARAMS:
        crit = {
            "title": title,
            "body": body,
            "authors": authors,
            "type": type,
            "last_updated": last_updated,
        }

        return {"criteria": crit}


class MessagesGetQuery(QueryOperator):
    """Query operators to pull message information"""

    def query(
        self,
        last_updated: datetime = Query(
            ...,
            title="Consumer ID",
        ),
    ) -> STORE_PARAMS:
        crit = {"last_updated": {"$gt": last_updated}}

        return {"criteria": crit}
