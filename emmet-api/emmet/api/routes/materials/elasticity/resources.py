from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.elasticity.query_operators import (
    BulkModulusQuery,
    ElasticityChemsysQuery,
    PoissonQuery,
    ShearModulusQuery,
)
from emmet.core.elasticity_legacy import ElasticityDoc
from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource


def elasticity_resource(elasticity_store):
    resource = ReadOnlyResource(
        elasticity_store,
        ElasticityDoc,
        query_operators=[
            ElasticityChemsysQuery(),
            BulkModulusQuery(),
            ShearModulusQuery(),
            PoissonQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ElasticityDoc,
                default_fields=["task_id", "pretty_formula"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Elasticity"],
        sub_path="/elasticity/",
        disable_validation=False,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
