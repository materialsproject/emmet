"""Perform a vectorized query on crystalline similarity."""

from fastapi import HTTPException, Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from emmet.core.similarity import CrystalNNSimilarity

from pymatgen.core import Structure


class SimilarityFeatureVectorQuery(QueryOperator):
    """Generate a feature-vector-based query."""

    def query(
        self,
        structure: Structure = Query(
            ..., description="A target structure for similarity searches."
        ),
        _limit: int = Query(
            10,
            description="Max number of entries to return in a single query. Limited to 10 by default",
        ),
    ) -> STORE_PARAMS:
        """Identify similar materials."""

        if not isinstance(structure, Structure):
            raise HTTPException(
                status_code=400, detail="Must provide a target structure."
            )

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "similarity_feature_vector",
                    "path": "feature_vector",
                    "queryVector": CrystalNNSimilarity()
                    ._featurize_structure(structure)
                    .tolist(),
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
