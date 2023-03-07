from maggma.api.resource import ReadOnlyResource
from emmet.core.molecules.thermo import ThermoDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery

from emmet.api.routes.mpcules.thermo.query_operators import (
    ThermoCorrectionQuery,
)
from emmet.api.routes.mpcules.molecules.query_operators import (
    MultiMPculeIDQuery,
    ExactCalcMethodQuery,
    FormulaQuery,
    ChemsysQuery,
    ElementsQuery,
    ChargeSpinQuery
)
from emmet.api.core.settings import MAPISettings
from emmet.api.core.global_header import GlobalHeaderProcessor


def thermo_resource(thermo_store):
    resource = ReadOnlyResource(
        thermo_store,
        ThermoDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            ExactCalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            ThermoCorrectionQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(ThermoDoc, default_fields=["molecule_id", "property_id", "solvent", "last_updated"],),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Thermo"],
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
