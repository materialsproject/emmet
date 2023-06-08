from __future__ import annotations

from emmet.api.routes._consumer.query_operator import (
    UserSettingsGetQuery,
    UserSettingsPostQuery,
)
from emmet.core._user_settings import UserSettingsDoc
from maggma.api.resource import SubmissionResource


def settings_resource(consumer_settings_store):
    resource = SubmissionResource(
        consumer_settings_store,
        UserSettingsDoc,
        post_query_operators=[UserSettingsPostQuery()],
        get_query_operators=[UserSettingsGetQuery()],
        enable_default_search=False,
        include_in_schema=False,
    )

    return resource
