from maggma.api.resource import ReadOnlyResource
from emmet.core.polar import DielectricDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.dielectric.query_operators import DielectricQuery
from emmet.api.core.global_header import GlobalHeaderProcessor


def dielectric_resource(dielectric_store):
    resource = ReadOnlyResource(
        dielectric_store,
        DielectricDoc,
        query_operators=[
            DielectricQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                DielectricDoc, default_fields=["material_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Dielectric"],
        disable_validation=True,
    )

    return resource
