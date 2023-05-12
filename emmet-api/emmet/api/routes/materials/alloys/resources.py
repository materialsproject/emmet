from maggma.api.resource import ReadOnlyResource

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery

from emmet.core.alloys import AlloyPairDoc

from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.alloys.query_operators import (
    MaterialIDsSearchQuery,
    FormulaSearchQuery,
)


def alloy_pairs_resource(alloy_pairs_store):
    resource = ReadOnlyResource(
        alloy_pairs_store,
        AlloyPairDoc,
        query_operators=[
            MaterialIDsSearchQuery(),
            FormulaSearchQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                AlloyPairDoc,
                default_fields=["pair_id"],
            ),
        ],
        tags=["Materials Alloys"],
        sub_path="/alloys/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
