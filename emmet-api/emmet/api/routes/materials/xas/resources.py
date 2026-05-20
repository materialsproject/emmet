from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    IdFormatQuery,
    MultiTaskIDQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.materials.query_operators import (
    ChemsysQuery,
    ElementsQuery,
    FormulaQuery,
)
from emmet.api.routes.materials.xas.query_operators import XASIDQuery, XASQuery
from emmet.core.types.typing import format_task_id
from emmet.core.xas import XASDoc, format_spectrum_id

XAS_SORT_FIELDS = [
    "material_id",
    "absorbing_element",
    "edge",
    "spectrum_type",
    "spectrum_id",
]


def xas_resource(xas_store):
    resource = ReadOnlyResource(
        xas_store,
        XASDoc,
        query_operators=[
            MultiTaskIDQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            XASQuery(),
            XASIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                XASDoc,
                default_fields=[
                    "task_id",
                    "edge",
                    "absorbing_element",
                    "formula_pretty",
                    "spectrum_type",
                    "last_updated",
                ],
            ),
            SortQuery(fields=XAS_SORT_FIELDS, max_num=1),
            # Optional response-side reformatting of the task_id and computed
            # spectrum_id fields based on the user's preferred display format.
            # No-op when the `id_format` query parameter is absent.
            IdFormatQuery(
                id_fields=[
                    ("task_id", format_task_id),
                    ("spectrum_id", format_spectrum_id),
                ]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials XAS"],
        sub_path="/xas/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,  # type: ignore
    )

    return resource
