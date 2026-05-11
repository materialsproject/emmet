from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    MultiMaterialIDQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.piezo.query_operators import PiezoelectricQuery
from emmet.core.polar import PiezoelectricDoc


def piezo_resource(piezo_store):
    resource = ReadOnlyResource(
        piezo_store,
        PiezoelectricDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            PiezoelectricQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                PiezoelectricDoc, default_fields=["material_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Piezoelectric"],
        sub_path="/piezoelectric/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
