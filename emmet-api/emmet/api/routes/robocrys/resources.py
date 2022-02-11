from maggma.api.resource import ReadOnlyResource
from maggma.api.resource.aggregation import AggregationResource
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery

from emmet.api.routes.robocrys.query_operators import RoboTextSearchQuery
from emmet.core.robocrys import RobocrystallogapherDoc
from emmet.api.core.global_header import GlobalHeaderProcessor


def robo_resource(robo_store):
    resource = ReadOnlyResource(
        robo_store,
        RobocrystallogapherDoc,
        query_operators=[
            PaginationQuery(),
            SparseFieldsQuery(
                RobocrystallogapherDoc, default_fields=["material_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Robocrystallographer"],
        disable_validation=True,
    )

    return resource


def robo_search_resource(robo_store):
    resource = AggregationResource(
        robo_store,
        RobocrystallogapherDoc,
        pipeline_query_operator=RoboTextSearchQuery(),
        tags=["Robocrystallographer"],
        sub_path="/text_search/",
        header_processor=GlobalHeaderProcessor(),
    )

    return resource
