"""Perform a vectorized query on crystalline similarity."""

from fastapi import HTTPException, Query

from emmet.core.similarity import SimilarityMethod, _vector_from_hex_and_norm

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS

SIM_METHOD_TO_FEAT_VEC_LENGTH = {
    SimilarityMethod.CRYSTALNN: 122,
    # SimilarityMethod.M3GNET: 128 # TODO: build out collection + test
}


class SimilarityFeatureVectorQuery(QueryOperator):
    """Generate a feature-vector-based query.

    The feature_vector_hex field is limited to 3_000 characters
    to prevent malicious submission of overly-long string data.

    In the worst case, a random unit vector of floats with
    length 130 has roughly a hex string length of 2,100 characters.

    Note that we pass unit vectors through only.
    Passing vectors with non-unit norm would increase the lenght of
    `feature_vector_hex` uncontrollably.
    """

    def query(
        self,
        feature_vector_hex: str = Query(
            ...,
            description="A compressed, hex representation of a row unit vector of floats.",
            max_length=3_000,
        ),
        feature_vector_norm: float = Query(
            ...,
            description="The norm of the feature vector",
        ),
        method: str | SimilarityMethod | None = Query(
            None,
            description="The method used to embed a structure as a feature vector.",
        ),
        _limit: int = Query(
            10,
            description="Max number of entries to return in a single query. Limited to 10 by default",
        ),
    ) -> STORE_PARAMS:
        """Identify similar materials."""

        feature_vector = _vector_from_hex_and_norm(
            feature_vector_hex, feature_vector_norm
        )
        if method is None:
            try:
                method = next(
                    method
                    for method, fvlen in SIM_METHOD_TO_FEAT_VEC_LENGTH.items()
                    if fvlen == len(feature_vector)
                )
            except StopIteration:
                raise ValueError(
                    "Unknown feature vector embedding method, input feature vector "
                    f"length = {len(feature_vector)} matches no known embedding method."
                )
        elif isinstance(method, str):
            method = (
                SimilarityMethod[method]
                if method in SimilarityMethod.__members__
                else SimilarityMethod(method)
            )

        ref_fv_len = SIM_METHOD_TO_FEAT_VEC_LENGTH[method]

        if (
            not isinstance(feature_vector, list | tuple)
            and not all(isinstance(x, float) for x in feature_vector)
            and not len(feature_vector) == ref_fv_len
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid feature vector for method {method.value}: "  # type: ignore[union-attr]
                    f"should be a list of {ref_fv_len} floats.",
                ),
            )

        index_name = "similarity_feature_vector"
        # because MongoDB does not permit renaming indexes,
        # and I was not forward thinking in naming it.
        # TODO: homogenize once we have other data built out
        if method != SimilarityMethod.CRYSTALNN:
            index_name += f"_{method.value.lower()}"  # type: ignore[union-attr]

        pipeline = [
            {
                "$vectorSearch": {
                    "index": index_name,
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
        self.total_doc = len(docs)
        return docs

    def meta(self):
        return {"total_doc": self.total_doc}

    def ensure_indexes(self):  # pragma: no cover
        return [("similarity_feature_vector", False)]
