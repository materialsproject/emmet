from maggma.api.resource import ReadOnlyResource
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.routes.materials.query_operators import DeprecationQuery

from emmet.core.provenance import ProvenanceDoc


def provenance_resource(provenance_store):
    resource = ReadOnlyResource(
        provenance_store,
        ProvenanceDoc,
        query_operators=[
            DeprecationQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ProvenanceDoc, default_fields=["material_id", "last_updated"]
            ),
        ],
        tags=["Provenance"],
        disable_validation=True,
    )

    return resource
