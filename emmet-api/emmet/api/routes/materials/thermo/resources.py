from maggma.api.query_operator.dynamic import NumericQuery
from maggma.api.resource import ReadOnlyResource
from emmet.core.thermo import ThermoDoc
from emmet.core.thermo import PhaseDiagramDoc

from maggma.api.query_operator import (
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from emmet.api.routes.materials.thermo.query_operators import (
    IsStableQuery,
    MultiThermoIDQuery,
    MultiThermoTypeQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.routes.materials.materials.query_operators import (
    MultiMaterialIDQuery,
    FormulaQuery,
    ChemsysQuery,
    LicenseQuery,
)
from emmet.api.core.settings import MAPISettings


def phase_diagram_resource(phase_diagram_store):
    resource = ReadOnlyResource(
        phase_diagram_store,
        PhaseDiagramDoc,
        tags=["Materials Thermo"],
        sub_path="/thermo/phase_diagram/",
        disable_validation=True,
        enable_default_search=False,
        header_processor=GlobalHeaderProcessor(),
        query_disk_use=False,
    )

    return resource


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
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ThermoDoc, default_fields=["thermo_id", "material_id", "last_updated"]
            ),
            LicenseQuery(),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Thermo"],
        sub_path="/thermo/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
