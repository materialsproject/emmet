from maggma.api.resource import ReadOnlyResource
from emmet.core.chemenv import ChemEnvDoc
from emmet.api.core.global_header import GlobalHeaderProcessor
from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.materials.query_operators import MultiMaterialIDQuery
from emmet.api.core.settings import MAPISettings


def chemenv_resource(chemenv_store):
    resource = ReadOnlyResource(
        chemenv_store,
        ChemEnvDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ChemEnvDoc,
                default_fields=["material_id", "formula_pretty", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Chemical Environment"],
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT
    )

    return resource
