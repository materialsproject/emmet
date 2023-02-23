from maggma.api.resource import ReadOnlyResource
from emmet.core.molecules.bonds import BondingDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery

from emmet.api.routes.mpcules.bonds.query_operators import (
    BondTypeLengthQuery,
)
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


def bonds_resource(bonds_store):
    resource = ReadOnlyResource(
        bonds_store,
        BondingDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            CalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MethodQuery(),
            BondTypeLengthQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(BondingDoc, default_fields=["molecule_id", "last_updated"],),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Bonds"],
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
