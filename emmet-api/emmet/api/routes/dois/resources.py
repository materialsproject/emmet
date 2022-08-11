from maggma.api.resource import ReadOnlyResource
from emmet.core.dois import DOIDoc
from emmet.api.core.global_header import GlobalHeaderProcessor
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.core.settings import MAPISettings


def dois_resource(dois_store):
    resource = ReadOnlyResource(
        dois_store,
        DOIDoc,
        query_operators=[
            PaginationQuery(),
            SparseFieldsQuery(DOIDoc, default_fields=["task_id", "doi"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["DOIs"],
        enable_default_search=False,
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
