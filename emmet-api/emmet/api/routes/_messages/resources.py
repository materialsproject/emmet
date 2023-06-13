from maggma.api.resource import SubmissionResource
from emmet.api.routes._messages.query_operator import (
    MessagesPostQuery,
    MessagesGetQuery,
)
from emmet.core._messages import MessagesDoc


def messages_resource(messages_store):
    resource = SubmissionResource(
        messages_store,
        MessagesDoc,
        post_query_operators=[MessagesPostQuery()],
        get_query_operators=[MessagesGetQuery()],
        include_in_schema=False,
    )

    return resource
