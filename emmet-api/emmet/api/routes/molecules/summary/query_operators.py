from dataclasses import dataclass

from fastapi import Query

from emmet.api.query_operator import InQuery
from emmet.api.utils import STORE_PARAMS


@dataclass
class MPculeIDsSearchQuery(InQuery):
    """
    Method to generate a query on summary docs using multiple molecule_id values
    """

    field_name: str = "molecule_id"

    def query(
        self,
        molecule_ids: str | None = Query(
            None, description="Comma-separated list of molecule_ids to query on"
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(molecule_ids)

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
