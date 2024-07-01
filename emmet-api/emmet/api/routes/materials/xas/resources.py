from maggma.api.resource import ReadOnlyResource
from emmet.core.xas import XASDoc

from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.api.routes.materials.materials.query_operators import (
    ElementsQuery,
    FormulaQuery,
    ChemsysQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.routes.materials.xas.query_operators import XASQuery, XASIDQuery
from emmet.api.core.settings import MAPISettings


def xas_resource(xas_store):
    resource = ReadOnlyResource(
        xas_store,
        XASDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            XASQuery(),
            XASIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                XASDoc,
                default_fields=[
                    "xas_id",
                    "task_id",
                    "edge",
                    "absorbing_element",
                    "formula_pretty",
                    "spectrum_type",
                    "last_updated",
                ],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials XAS"],
        sub_path="/xas/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,  # type: ignore
    )

    return resource
