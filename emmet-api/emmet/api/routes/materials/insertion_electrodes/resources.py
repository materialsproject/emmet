from emmet.api.query_operator import (
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.core.electrode import InsertionElectrodeDoc
from emmet.api.core.global_header import GlobalHeaderProcessor

from emmet.api.routes.materials.insertion_electrodes.query_operators import (
    ElectrodeFormulaQuery,
    ElectrodeElementsQuery,
    ElectrodesChemsysQuery,
    WorkingIonQuery,
    MultiBatteryIDQuery,
)

from emmet.api.core.settings import MAPISettings

sort_fields = [
    "max_delta_volume",
    "average_voltage",
    "capacity_grav",
    "capacity_vol",
    "energy_grav",
    "energy_vol",
    "stability_charge",
    "stability_discharge",
]


def insertion_electrodes_resource(insertion_electrodes_store):
    resource = ReadOnlyResource(
        insertion_electrodes_store,
        InsertionElectrodeDoc,
        query_operators=[
            MultiBatteryIDQuery(),
            ElectrodeFormulaQuery(),
            ElectrodesChemsysQuery(),
            WorkingIonQuery(),
            ElectrodeElementsQuery(),
            NumericQuery(model=InsertionElectrodeDoc),
            PaginationQuery(),
            SparseFieldsQuery(
                InsertionElectrodeDoc,
                default_fields=["battery_id", "last_updated"],
            ),
            SortQuery(fields=sort_fields, max_num=1),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Electrodes"],
        sub_path="/insertion_electrodes/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
