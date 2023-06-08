from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.electrodes.query_operators import (
    ElectrodeElementsQuery,
    ElectrodeFormulaQuery,
    ElectrodeMultiMaterialIDQuery,
    ElectrodesChemsysQuery,
    MultiBatteryIDQuery,
    WorkingIonQuery,
)
from emmet.core.electrode import InsertionElectrodeDoc
from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from maggma.api.query_operator.dynamic import NumericQuery
from maggma.api.resource import ReadOnlyResource


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
