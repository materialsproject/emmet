from maggma.api.resource import ReadOnlyResource
from emmet.core.bonds import BondingDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery

from emmet.api.routes.materials.bonds.query_operators import (
    BondLengthQuery,
    CoordinationEnvsQuery,
)
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.core.settings import MAPISettings
from emmet.api.core.global_header import GlobalHeaderProcessor


def bonds_resource(bonds_store):
    resource = ReadOnlyResource(
        bonds_store,
        BondingDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            BondLengthQuery(),
            CoordinationEnvsQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                BondingDoc,
                default_fields=["material_id", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Bonds"],
        sub_path="/bonds/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
