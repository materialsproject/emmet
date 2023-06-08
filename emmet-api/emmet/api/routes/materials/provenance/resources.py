from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.materials.query_operators import (
    DeprecationQuery,
    MultiMaterialIDQuery,
)
from emmet.core.provenance import ProvenanceDoc
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource


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
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Provenance"],
        sub_path="/provenance/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
