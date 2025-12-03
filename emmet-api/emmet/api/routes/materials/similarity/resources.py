from emmet.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.resource import ReadOnlyResource
from emmet.api.resource.aggregation import AggregationResource
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.routes.materials.similarity.query_operators import (
    SimilarityFeatureVectorQuery,
)

from emmet.core.similarity import SimilarityDoc

timeout = MAPISettings().TIMEOUT


def similarity_resource(similarity_store):
    resource = ReadOnlyResource(
        similarity_store,
        SimilarityDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(SimilarityDoc, default_fields=["material_id"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Similarity"],
        sub_path="/similarity/",
        disable_validation=True,
        timeout=timeout,
    )

    return resource


def similarity_feature_vector_resource(similarity_store):
    """Vector search on crystalline similarity feature vectors."""
    return AggregationResource(
        similarity_store,
        SimilarityDoc,
        pipeline_query_operator=SimilarityFeatureVectorQuery(),
        sub_path="/similarity/match/",
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Similarity"],
        timeout=timeout,
    )
