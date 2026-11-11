from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    IdFormatQuery,
    NumericQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.materials.query_operators import (
    ChemsysQuery,
    ElementsQuery,
    FormulaQuery,
    SymmetryQuery,
)
from emmet.api.routes.materials.phonon.query_operators import (
    MultiPhononIDQuery,
    PhononMethodQuery,
)
from emmet.core.phonon import PhononBSDOSTask


def phonon_bsdos_resource(phonon_bs_store):
    resource = ReadOnlyResource(
        phonon_bs_store,
        PhononBSDOSTask,
        query_operators=[
            MultiPhononIDQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            SymmetryQuery(),
            PhononMethodQuery(),
            NumericQuery(model=PhononBSDOSTask, excluded_fields=["composition"]),
            PaginationQuery(),
            SparseFieldsQuery(
                PhononBSDOSTask, default_fields=["identifier", "last_updated"]
            ),
            IdFormatQuery(model=PhononBSDOSTask),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Phonon"],
        sub_path="/phonon/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,  # type: ignore
    )

    return resource
