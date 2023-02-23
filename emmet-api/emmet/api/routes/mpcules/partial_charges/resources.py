from maggma.api.resource import ReadOnlyResource
from emmet.core.molecules.atomic import PartialChargesDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery

from emmet.api.routes.mpcules.molecules.query_operators import (
    MultiMPculeIDQuery,
    CalcMethodQuery,
    FormulaQuery,
    ChemsysQuery,
    ElementsQuery,
    ChargeSpinQuery
)
from emmet.api.routes.mpcules.utils import MethodQuery
from emmet.api.core.settings import MAPISettings
from emmet.api.core.global_header import GlobalHeaderProcessor


def charges_resource(charges_store):
    resource = ReadOnlyResource(
        charges_store,
        PartialChargesDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            CalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MethodQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(PartialChargesDoc, default_fields=["molecule_id", "last_updated"],),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["PartialCharges"],
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
