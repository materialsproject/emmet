from maggma.api.resource import ReadOnlyResource
from emmet.core.polar import PiezoelectricDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.piezo.query_operators import PiezoelectricQuery
from emmet.api.core.global_header import GlobalHeaderProcessor


def piezo_resource(piezo_store):
    resource = ReadOnlyResource(
        piezo_store,
        PiezoelectricDoc,
        query_operators=[
            PiezoelectricQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                PiezoelectricDoc, default_fields=["material_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Piezoelectric"],
        disable_validation=True,
    )

    return resource
