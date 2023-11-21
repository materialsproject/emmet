from maggma.api.resource import ReadOnlyResource
from emmet.core.elasticity import ElasticityDoc
from emmet.api.core.global_header import GlobalHeaderProcessor
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.routes.materials.elasticity.query_operators import (
    ElasticityChemsysQuery,
    BulkModulusQuery,
    ShearModulusQuery,
    PoissonQuery,
)

from emmet.api.core.settings import MAPISettings


def elasticity_resource(elasticity_store):
    resource = ReadOnlyResource(
        elasticity_store,
        ElasticityDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            ElasticityChemsysQuery(),
            BulkModulusQuery(),
            ShearModulusQuery(),
            PoissonQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ElasticityDoc,
                default_fields=["material_id", "formula_pretty"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Elasticity"],
        sub_path="/elasticity/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
