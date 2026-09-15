from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    IdFormatQuery,
    MultiMaterialIDQuery,
    NumericQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.chemenv.query_operators import ChemEnvQuery
from emmet.api.routes.materials.materials.query_operators import (
    ElementsQuery,
    LicenseQuery,
)
from emmet.core.chemenv import ChemEnvDoc
from emmet.core.types.typing import format_identifier


def chemenv_resource(chemenv_store):
    resource = ReadOnlyResource(
        chemenv_store,
        ChemEnvDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            ChemEnvQuery(),
            ElementsQuery(),
            NumericQuery(model=ChemEnvDoc, excluded_fields=["valences"]),
            PaginationQuery(),
            SparseFieldsQuery(
                ChemEnvDoc,
                default_fields=["material_id", "formula_pretty", "last_updated"],
            ),
            LicenseQuery(),
            IdFormatQuery([("material_id", format_identifier)]),
        ],
        header_processor=GlobalHeaderProcessor(),
        query_to_configure_on_request=LicenseQuery(),
        tags=["Materials Chemical Environment"],
        sub_path="/chemenv/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
