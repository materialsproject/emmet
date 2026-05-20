from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    MultiMaterialIDQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.resource.aggregation import AggregationResource
from emmet.api.routes.materials.robocrys.query_operators import RoboTextSearchQuery
from emmet.core.robocrys import RobocrystallogapherDoc

timeout = MAPISettings().TIMEOUT


def robo_resource(robo_store):
    resource = ReadOnlyResource(
        robo_store,
        RobocrystallogapherDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                RobocrystallogapherDoc, default_fields=["material_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Robocrystallographer"],
        sub_path="/robocrys/",
        disable_validation=True,
        timeout=timeout,
    )

    return resource


def robo_search_resource(robo_store):
    resource = AggregationResource(
        robo_store,
        RobocrystallogapherDoc,
        pipeline_query_operator=RoboTextSearchQuery(),
        sub_path="/robocrys/text_search/",
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Robocrystallographer"],
        timeout=timeout,
    )

    return resource
