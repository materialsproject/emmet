from fastapi import HTTPException, Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class RoboTextSearchQuery(QueryOperator):
    """
    Method to generate a robocrystallographer text search query
    """

    def query(
        self,
        keywords: str = Query(
            ...,
            description="Comma delimited string keywords to search robocrystallographer description text with",
        ),
        _skip: int = Query(0, description="Number of entries to skip in the search"),
        _limit: int = Query(
            1000,
            description="Max number of entries to return in a single query. Limited to 1000 by default",
        ),
    ) -> STORE_PARAMS:
        if not keywords.strip():
            raise HTTPException(status_code=400, detail="Must provide search keywords.")

        pipeline = [
            {
                "$search": {
                    "index": "description",
                    "regex": {
                        "query": [word.strip() for word in keywords.split(",") if word],
                        "path": "description",
                        "allowAnalyzedField": True,
                    },
                    "sort": {"score": {"$meta": "searchScore"}, "description": 1},
                    "count": {"type": "total"},
                }
            },
            {"$skip": _skip},
            {"$limit": _limit},
            {
                "$project": {
                    "_id": 0,
                    "meta": "$$SEARCH_META",
                    "material_id": 1,
                    "description": 1,
                    "condensed_structure": 1,
                    "last_updated": 1,
                }
            },
        ]
        return {"pipeline": pipeline}

    def post_process(self, docs, query):
        self.total_doc = docs[0]["meta"]["count"]["total"]
        return docs

    def meta(self):
        return {"total_doc": self.total_doc}

    def ensure_indexes(self):  # pragma: no cover
        return [("description", False)]
