from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery

from emmet.core.similarity import SimilarityDoc


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
        timeout=MAPISettings().TIMEOUT,  # type: ignore
    )

    return resource
