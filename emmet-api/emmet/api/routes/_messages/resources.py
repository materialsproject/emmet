from emmet.api.resource import SubmissionResource
from emmet.api.routes._messages.query_operator import (
    MessagesPostQuery,
    MessagesGetQuery,
)
from emmet.api.query_operator import PaginationQuery, SparseFieldsQuery, SortQuery
from emmet.core._messages import MessagesDoc
from emmet.api.core.settings import MAPISettings


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
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
