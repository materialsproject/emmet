from maggma.api.query_operator.dynamic import NumericQuery
from maggma.api.resource import ReadOnlyResource
from emmet.core.electrode import InsertionElectrodeDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.electrodes.query_operators import (
    ElectrodeFormulaQuery,
    ElectrodeElementsQuery,
    ElectrodesChemsysQuery,
    WorkingIonQuery,
)


def insertion_electrodes_resource(insertion_electrodes_store):
    resource = ReadOnlyResource(
        insertion_electrodes_store,
        InsertionElectrodeDoc,
        query_operators=[
            ElectrodeFormulaQuery(),
            ElectrodesChemsysQuery(),
            WorkingIonQuery(),
            ElectrodeElementsQuery(),
            NumericQuery(model=InsertionElectrodeDoc),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                InsertionElectrodeDoc, default_fields=["battery_id", "last_updated"],
            ),
        ],
        tags=["Electrodes"],
        disable_validation=True,
    )

    return resource
