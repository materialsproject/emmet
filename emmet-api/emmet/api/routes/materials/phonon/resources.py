from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource

from emmet.core.phonon import PhononBSDOSDoc
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings


def phonon_bsdos_resource(phonon_bs_store):
    resource = ReadOnlyResource(
        phonon_bs_store,
        PhononBSDOSDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                PhononBSDOSDoc, default_fields=["material_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Phonon"],
        sub_path="/phonon/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,  # type: ignore
    )

    return resource
