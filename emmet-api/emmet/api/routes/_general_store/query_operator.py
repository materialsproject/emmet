from fastapi import Body, Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class GeneralStorePostQuery(QueryOperator):
    """Query operators to provide general store information to post"""

    def query(
        self,
        kind: str = Query(..., title="Data type"),
        markdown: str = Query(None, title="Markdown data"),
        meta: dict = Body(None, title="Metadata"),
    ) -> STORE_PARAMS:
        crit = {"kind": kind, "markdown": markdown, "meta": meta}

        return {"criteria": crit}

    def post_process(self, docs, query):
        d = [
            {
                "kind": query["criteria"]["kind"],
                "markdown": query["criteria"].get("markdown", None),
                "meta": query["criteria"].get("meta", None),
            }
        ]

        return d


class GeneralStoreGetQuery(QueryOperator):
    """Query operators to obtain general store information"""

    def query(self, kind: str = Query(..., title="Data type")) -> STORE_PARAMS:
        crit = {"kind": kind}

        return {"criteria": crit}
