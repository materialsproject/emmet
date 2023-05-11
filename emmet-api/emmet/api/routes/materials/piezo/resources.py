from maggma.api.resource import ReadOnlyResource
from emmet.core.polar import PiezoelectricDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.materials.piezo.query_operators import PiezoelectricQuery
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings


def piezo_resource(piezo_store):
    resource = ReadOnlyResource(
        piezo_store,
        PiezoelectricDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            PiezoelectricQuery(),
            SortQuery(),
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
