from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.query_operator.core import MultiMaterialIDQuery
from emmet.api.query_operator.dynamic import NumericQuery
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.materials.query_operators import (
    ChemsysQuery,
    FormulaQuery,
    LicenseQuery,
)
from emmet.api.routes.materials.thermo.query_operators import (
    IsStableQuery,
    MultiThermoIDQuery,
    MultiThermoTypeQuery,
)
from emmet.core.thermo import ThermoDoc


def thermo_resource(thermo_store):
    resource = ReadOnlyResource(
        thermo_store,
        ThermoDoc,
        query_operators=[
            MultiThermoIDQuery(),
            MultiMaterialIDQuery(),
            MultiThermoTypeQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            IsStableQuery(),
            NumericQuery(model=ThermoDoc),
            PaginationQuery(),
            SparseFieldsQuery(
                ThermoDoc, default_fields=["thermo_id", "material_id", "last_updated"]
            ),
            LicenseQuery(),
        ],
        header_processor=GlobalHeaderProcessor(),
        query_to_configure_on_request=LicenseQuery(),
        tags=["Materials Thermo"],
        sub_path="/thermo/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
