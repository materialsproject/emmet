from maggma.api.resource import ReadOnlyResource
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.routes.materials.query_operators import DeprecationQuery, MultiMaterialIDQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.core.provenance import ProvenanceDoc
from emmet.api.core.settings import MAPISettings


def provenance_resource(provenance_store):
    resource = ReadOnlyResource(
        provenance_store,
        ProvenanceDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            DeprecationQuery(),
            PaginationQuery(),
            SparseFieldsQuery(ProvenanceDoc, default_fields=["material_id", "last_updated"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Provenance"],
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
