from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery, NumericQuery
from maggma.api.resource import ReadOnlyResource

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.routes.materials.chemenv.query_operators import ChemEnvQuery
from emmet.core.chemenv import ChemEnvDoc


def chemenv_resource(chemenv_store):
    resource = ReadOnlyResource(
        chemenv_store,
        ChemEnvDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            ChemEnvQuery(),
            NumericQuery(model=ChemEnvDoc, excluded_fields=["valences"]),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(ChemEnvDoc, default_fields=["material_id", "formula_pretty", "last_updated"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Chemical Environment"],
        disable_validation=True,
        timeout=MAPISettings(DB_VERSION="").TIMEOUT,
        sub_path="/chemenv/",
    )

    return resource
