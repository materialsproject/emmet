from maggma.api.resource import ReadOnlyResource
from emmet.core.xas import XASDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.materials.materials.query_operators import (
    ElementsQuery,
    FormulaQuery,
    ChemsysQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.routes.materials.xas.query_operators import XASQuery, XASTaskIDQuery
from emmet.api.core.settings import MAPISettings


def xas_resource(xas_store):
    resource = ReadOnlyResource(
        xas_store,
        XASDoc,
        query_operators=[
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            XASQuery(),
            XASTaskIDQuery(),
            SortQuery(),
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
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
