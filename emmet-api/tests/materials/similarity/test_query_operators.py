"""Test crystalline similarity vector search."""

import numpy as np
import pytest

from emmet.core.similarity import (
    SimilarityMethod,
    _vector_to_hex_and_norm,
    _vector_from_hex_and_norm,
)
from emmet.api.routes.materials.similarity.query_operators import (
    SimilarityFeatureVectorQuery,
    SIM_METHOD_TO_FEAT_VEC_LENGTH,
)


@pytest.mark.parametrize(
    "method", [None, "CrystalNN", "CRYSTALNN", SimilarityMethod.CRYSTALNN]
)
def test_similarity_structure_search(test_dir, method):

    op = SimilarityFeatureVectorQuery()
    fv = np.random.rand(
        SIM_METHOD_TO_FEAT_VEC_LENGTH[SimilarityMethod.CRYSTALNN]
    ).tolist()
    fv_hex, fv_norm = _vector_to_hex_and_norm(fv)

    limit = 10
    q = {
        "pipeline": [
            {
                "$vectorSearch": {
                    "index": "similarity_feature_vector",
                    "path": "feature_vector",
                    "queryVector": _vector_from_hex_and_norm(fv_hex, fv_norm),
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

    manual_q = op.query(
        feature_vector_hex=fv_hex,
        feature_vector_norm=fv_norm,
        method=method,
        _limit=limit,
    )
    assert manual_q == q

    doc = [{"meta": {"count": {"total": limit}}}]
    assert op.post_process(doc, q) == doc
    assert "total_doc" in op.meta()
