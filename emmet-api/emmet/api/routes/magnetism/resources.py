from maggma.api.resource import ReadOnlyResource
from emmet.core.magnetism import MagnetismDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.magnetism.query_operators import MagneticQuery
from emmet.api.routes.materials.query_operators import MultiMaterialIDQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings


def magnetism_resource(magnetism_store):
    resource = ReadOnlyResource(
        magnetism_store,
        MagnetismDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            MagneticQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(MagnetismDoc, default_fields=["material_id", "last_updated"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Magnetism"],
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
