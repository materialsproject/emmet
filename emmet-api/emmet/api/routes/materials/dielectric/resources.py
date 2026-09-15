from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    IdFormatQuery,
    MultiMaterialIDQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.dielectric.query_operators import DielectricQuery
from emmet.core.polar import DielectricDoc
from emmet.core.types.typing import format_identifier


def dielectric_resource(dielectric_store):
    resource = ReadOnlyResource(
        dielectric_store,
        DielectricDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            DielectricQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                DielectricDoc, default_fields=["material_id", "last_updated"]
            ),
            IdFormatQuery([("material_id", format_identifier)]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Dielectric"],
        sub_path="/dielectric/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
