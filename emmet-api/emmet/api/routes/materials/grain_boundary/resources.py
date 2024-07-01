from maggma.api.resource import ReadOnlyResource
from emmet.core.grain_boundary import GrainBoundaryDoc

from emmet.api.routes.materials.grain_boundary.query_operators import (
    GBStructureQuery,
    GBTaskIDQuery,
)
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from maggma.api.query_operator import (
    PaginationQuery,
    SparseFieldsQuery,
    NumericQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings


def gb_resource(gb_store):
    resource = ReadOnlyResource(
        gb_store,
        GrainBoundaryDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            GBTaskIDQuery(),
            NumericQuery(
                model=GrainBoundaryDoc, excluded_fields=["rotation_axis", "gb_plane"]
            ),
            GBStructureQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                GrainBoundaryDoc, default_fields=["task_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Grain Boundaries"],
        sub_path="/grain_boundaries/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,  # type: ignore
    )

    return resource
