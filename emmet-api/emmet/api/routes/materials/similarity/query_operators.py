"""Perform a vectorized query on crystalline similarity."""

from fastapi import HTTPException, Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class SimilarityFeatureVectorQuery(QueryOperator):
    """Generate a feature-vector-based query.

    TODO: Add an `embedding` kwarg to select between
    multiple embedding methods used to gauge
    similarity (e.g., ML-based metrics.)
    """

    def query(
        self,
        feature_vector: list[float] = Query(
            ..., description="A row vector of floats representing a structure."
        ),
        # embedding : Literal["CrystalNN"] = Query(
        #     "CrystalNN",
        #     description="The method used to embed a structure as a feature vector."
        # ),
        _limit: int = Query(
            10,
            description="Max number of entries to return in a single query. Limited to 10 by default",
        ),
    ) -> STORE_PARAMS:
        """Identify similar materials."""

        if (
            not isinstance(feature_vector, list | tuple)
            and not all(isinstance(x, float) for x in feature_vector)
            and not len(feature_vector) == 122
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid feature vector: should be a list of 122 floats.",
            )

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "similarity_feature_vector",
                    "path": "feature_vector",
                    "queryVector": feature_vector,
                    "numCandidates": _limit,
                    "limit": _limit,
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "material_id": 1,
                    "formula_pretty": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        return {
            "pipeline": pipeline,
        }

    def post_process(self, docs, query):
        self.total_doc = docs[0]["meta"]["count"]["total"]
        return docs

    def meta(self):
        return {"total_doc": self.total_doc}

    def ensure_indexes(self):  # pragma: no cover
        return [("similarity_feature_vector", False)]
