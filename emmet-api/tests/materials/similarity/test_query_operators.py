"""Test crystalline similarity vector search."""

import pytest

from emmet.core.similarity import SimilarityMethod
from emmet.api.routes.materials.similarity.query_operators import (
    SimilarityFeatureVectorQuery,
    SIM_METHOD_TO_FEAT_VEC_LENGTH,
)
import numpy as np


@pytest.mark.parametrize(
    "method", [None, "CrystalNN", "CRYSTALNN", SimilarityMethod.CRYSTALNN]
)
def test_similarity_structure_search(test_dir, method):

    op = SimilarityFeatureVectorQuery()
    fv = np.random.rand(
        SIM_METHOD_TO_FEAT_VEC_LENGTH[SimilarityMethod.CRYSTALNN]
    ).tolist()
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

    manual_q = op.query(feature_vector=fv, method=method, _limit=limit)
    assert manual_q == q

    doc = [{"meta": {"count": {"total": limit}}}]
    assert op.post_process(doc, q) == doc
    assert op.meta() == {"total_doc": limit}
