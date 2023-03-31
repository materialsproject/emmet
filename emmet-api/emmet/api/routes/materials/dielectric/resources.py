from maggma.api.resource import ReadOnlyResource
from emmet.core.polar import DielectricDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.materials.dielectric.query_operators import DielectricQuery
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings


def dielectric_resource(dielectric_store):
    resource = ReadOnlyResource(
        dielectric_store,
        DielectricDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            DielectricQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(DielectricDoc, default_fields=["material_id", "last_updated"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Dielectric"],
        disable_validation=True,
        timeout=MAPISettings(DB_VERSION="").TIMEOUT,
        sub_path="/dielectric/",
    )

    return resource
