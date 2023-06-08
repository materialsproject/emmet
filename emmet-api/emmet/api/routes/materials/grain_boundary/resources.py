from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.grain_boundary.query_operators import (
    GBStructureQuery,
    GBTaskIDQuery,
)
from emmet.core.grain_boundary import GrainBoundaryDoc
from maggma.api.query_operator import (
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from maggma.api.resource import ReadOnlyResource


def gb_resource(gb_store):
    resource = ReadOnlyResource(
        gb_store,
        GrainBoundaryDoc,
        query_operators=[
            GBTaskIDQuery(),
            NumericQuery(
                model=GrainBoundaryDoc, excluded_fields=["rotation_axis", "gb_plane"]
            ),
            GBStructureQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                GrainBoundaryDoc, default_fields=["task_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Grain Boundaries"],
        sub_path="/grain_boundary/",
        enable_get_by_key=False,
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
