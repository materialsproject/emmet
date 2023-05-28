from typing import Optional
from fastapi import Query

from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class MPculeIDsSearchQuery(QueryOperator):
    """
    Method to generate a query on summary docs using multiple molecule_id values
    """

    def query(
        self,
        molecule_ids: Optional[str] = Query(
            None, description="Comma-separated list of molecule_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if molecule_ids:
            crit.update(
                {
                    "molecule_id": {
                        "$in": [
                            molecule_id.strip()
                            for molecule_id in molecule_ids.split(",")
                        ]
                    }
                }
            )

        return {"criteria": crit}

    def post_process(self, docs, query):
        if not query.get("sort", None):
            mpcule_ids = (
                query.get("criteria", {}).get("molecule_id", {}).get("$in", None)
            )

            if mpcule_ids is not None and "molecule_id" in query.get("properties", []):
                mpculeid_mapping = {
                    mpculeid: ind for ind, mpculeid in enumerate(mpcule_ids)
                }

                docs = sorted(docs, key=lambda d: mpculeid_mapping[d["molecule_id"]])

        return docs
