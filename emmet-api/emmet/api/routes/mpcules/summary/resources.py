from emmet.core.molecules.summary import SummaryDoc

from maggma.api.query_operator import (
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
    NumericQuery,
)
from maggma.api.resource import ReadOnlyResource
from emmet.api.routes.mpcules.molecules.query_operators import (
    FormulaQuery,
    ChemsysQuery,
    ElementsQuery,
    ChargeSpinQuery,
    DeprecationQuery,
)
from emmet.api.routes.summary.query_operators import (HasPropsQuery)
from emmet.api.routes.mpcules.summary.hint_scheme import SummaryHintScheme
from emmet.api.routes.mpcules.summary.query_operators import (MPculeIDsSearchQuery)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings

timeout = MAPISettings().TIMEOUT


def summary_resource(summary_store):
    resource = ReadOnlyResource(
        summary_store,
        SummaryDoc,
        query_operators=[
            MPculeIDsSearchQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            NumericQuery(model=SummaryDoc, excluded_fields=["composition"]),
            HasPropsQuery(),
            ChargeSpinQuery(),
            DeprecationQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(SummaryDoc, default_fields=["molecule_id"]),
        ],
        hint_scheme=SummaryHintScheme(),
        header_processor=GlobalHeaderProcessor(),
        tags=["Summary"],
        disable_validation=True,
        timeout=timeout
    )

    return resource
