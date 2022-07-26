from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings

from emmet.core.similarity import SimilarityDoc


def similarity_resource(similarity_store):
    resource = ReadOnlyResource(
        similarity_store,
        SimilarityDoc,
        query_operators=[
            PaginationQuery(),
            SparseFieldsQuery(SimilarityDoc, default_fields=["material_id"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Similarity"],
        enable_default_search=False,
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT
    )

    return resource
