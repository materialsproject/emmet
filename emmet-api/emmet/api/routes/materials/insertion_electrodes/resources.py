from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    IdFormatQuery,
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.insertion_electrodes.query_operators import (
    ElectrodeElementsQuery,
    ElectrodeFormulaQuery,
    ElectrodesChemsysQuery,
    MultiBatteryIDQuery,
    WorkingIonQuery,
)
from emmet.core.electrode import InsertionElectrodeDoc
from emmet.core.types.typing import format_identifier

sort_fields = [
    "battery_id",
    "max_delta_volume",
    "average_voltage",
    "capacity_grav",
    "capacity_vol",
    "energy_grav",
    "energy_vol",
    "stability_charge",
    "stability_discharge",
    "working_ion",
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
            IdFormatQuery(
                [
                    ("material_ids", format_identifier),
                    ("id_charge", format_identifier),
                    ("id_discharge", format_identifier),
                ]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Electrodes"],
        sub_path="/insertion_electrodes/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
