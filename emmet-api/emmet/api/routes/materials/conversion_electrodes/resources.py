from emmet.api.query_operator.dynamic import NumericQuery
from emmet.api.resource import ReadOnlyResource
from emmet.core.electrode import ConversionElectrodeDoc
from emmet.api.core.global_header import GlobalHeaderProcessor

from emmet.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.routes.materials.insertion_electrodes.query_operators import (
    WorkingIonQuery,
    MultiBatteryIDQuery,
)

from emmet.api.core.settings import MAPISettings


def conversion_electrodes_resource(conversion_electrodes_store):
    resource = ReadOnlyResource(
        conversion_electrodes_store,
        ConversionElectrodeDoc,
        query_operators=[
            MultiBatteryIDQuery(),
            WorkingIonQuery(),
            NumericQuery(model=ConversionElectrodeDoc),
            PaginationQuery(),
            SparseFieldsQuery(
                ConversionElectrodeDoc,
                default_fields=["battery_id", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Electrodes"],
        sub_path="/conversion_electrodes/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
