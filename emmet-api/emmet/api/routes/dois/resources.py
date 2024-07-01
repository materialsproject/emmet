from maggma.api.resource import ReadOnlyResource
from emmet.core.dois import DOIDoc
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.core.settings import MAPISettings


def dois_resource(dois_store):
    resource = ReadOnlyResource(
        dois_store,
        DOIDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(DOIDoc, default_fields=["material_id", "doi"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["DOIs"],
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,  # type: ignore
    )

    return resource
