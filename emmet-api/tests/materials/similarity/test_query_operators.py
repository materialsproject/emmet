"""Test crystalline similarity vector search."""

from emmet.api.routes.materials.similarity.query_operators import (
    SimilarityFeatureVectorQuery,
)
from emmet.core.similarity import CrystalNNSimilarity
from pymatgen.core import Structure


def test_similarity_structure_search(test_dir):

    op = SimilarityFeatureVectorQuery()
    structure = Structure.from_file(test_dir / "Si_mp_149.cif")
    fv = CrystalNNSimilarity()._featurize_structure(structure).tolist()

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
