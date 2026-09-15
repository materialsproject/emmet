from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    DeprecationQuery,
    IdFormatQuery,
    MultiMaterialIDQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.core.provenance import ProvenanceDoc
from emmet.core.types.typing import format_identifier


def provenance_resource(provenance_store):
    resource = ReadOnlyResource(
        provenance_store,
        ProvenanceDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            DeprecationQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ProvenanceDoc, default_fields=["material_id", "last_updated"]
            ),
            IdFormatQuery([("material_id", format_identifier)]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Provenance"],
        sub_path="/provenance/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
