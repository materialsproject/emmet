"""Test crystalline similarity vector search."""

from emmet.api.routes.materials.similarity.query_operators import (
    SimilarityFeatureVectorQuery,
)
import numpy as np


def test_similarity_structure_search(test_dir):

    op = SimilarityFeatureVectorQuery()
    fv = np.random.rand(122).tolist()
    limit = 10
    q = {
        "pipeline": [
            {
                "$vectorSearch": {
                    "index": "similarity_feature_vector",
                    "path": "feature_vector",
                    "queryVector": fv,
                    "numCandidates": limit,
                    "limit": limit,
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
    }

    manual_q = op.query(feature_vector=fv, _limit=limit)
    assert manual_q == q

    doc = [{"meta": {"count": {"total": limit}}}]
    assert op.post_process(doc, q) == doc
    assert op.meta() == {"total_doc": limit}
