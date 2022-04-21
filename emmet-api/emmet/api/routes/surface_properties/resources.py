from email import header
from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from maggma.api.query_operator.dynamic import NumericQuery
from maggma.api.resource import ReadOnlyResource

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.routes.surface_properties.query_operators import ReconstructedQuery
from emmet.core.surface_properties import SurfacePropDoc


def surface_props_resource(surface_prop_store):
    resource = ReadOnlyResource(
        surface_prop_store,
        SurfacePropDoc,
        query_operators=[
            NumericQuery(model=SurfacePropDoc),
            ReconstructedQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(SurfacePropDoc, default_fields=["task_id"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Surface Properties"],
        disable_validation=True,
    )

    return resource
