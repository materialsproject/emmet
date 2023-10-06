from maggma.api.query_operator.dynamic import NumericQuery
from maggma.api.resource import ReadOnlyResource
from emmet.core.electrode import InsertionElectrodeDoc
from emmet.api.core.global_header import GlobalHeaderProcessor

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.materials.insertion_electrodes.query_operators import (
    ElectrodeFormulaQuery,
    ElectrodeElementsQuery,
    ElectrodesChemsysQuery,
    WorkingIonQuery,
    ElectrodeMultiMaterialIDQuery,
    MultiBatteryIDQuery,
)

from emmet.api.core.settings import MAPISettings


def insertion_electrodes_resource(insertion_electrodes_store):
    resource = ReadOnlyResource(
        insertion_electrodes_store,
        InsertionElectrodeDoc,
        query_operators=[
            MultiBatteryIDQuery(),
            ElectrodeMultiMaterialIDQuery(),
            ElectrodeFormulaQuery(),
            ElectrodesChemsysQuery(),
            WorkingIonQuery(),
            ElectrodeElementsQuery(),
            NumericQuery(model=InsertionElectrodeDoc),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                InsertionElectrodeDoc,
                default_fields=["battery_id", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Electrodes"],
        sub_path="/insertion_electrodes/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
