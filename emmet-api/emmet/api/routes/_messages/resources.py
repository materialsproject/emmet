from maggma.api.resource import SubmissionResource
from emmet.api.routes._messages.query_operator import (
    MessagesPostQuery,
    MessagesGetQuery,
)
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery, SortQuery
from emmet.core._messages import MessagesDoc


def messages_resource(messages_store):
    resource = SubmissionResource(
        messages_store,
        MessagesDoc,
        post_query_operators=[MessagesPostQuery()],
        get_query_operators=[
            MessagesGetQuery(),
            PaginationQuery(),
            SortQuery(),
            SparseFieldsQuery(
                model=MessagesDoc, default_fields=["title", "body", "last_updated"]
            ),
        ],
        include_in_schema=False,
    )

    return resource
