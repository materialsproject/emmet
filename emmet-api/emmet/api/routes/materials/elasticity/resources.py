from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    MultiMaterialIDQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.elasticity.query_operators import (
    BulkModulusQuery,
    ElasticityChemsysQuery,
    PoissonQuery,
    ShearModulusQuery,
)
from emmet.core.elasticity import ElasticityDoc


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
