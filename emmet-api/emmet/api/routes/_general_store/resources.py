from __future__ import annotations

from emmet.api.routes._general_store.query_operator import (
    GeneralStoreGetQuery,
    GeneralStorePostQuery,
)
from emmet.core._general_store import GeneralStoreDoc
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from maggma.api.resource import SubmissionResource


def general_store_resource(general_store):
    resource = SubmissionResource(
        general_store,
        GeneralStoreDoc,
        post_query_operators=[GeneralStorePostQuery()],
        get_query_operators=[
            GeneralStoreGetQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                model=GeneralStoreDoc,
                default_fields=["kind", "markdown", "meta", "last_updated"],
            ),
        ],
        enable_default_search=True,
        include_in_schema=False,
        calculate_submission_id=True,
    )

    return resource
