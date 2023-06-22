from maggma.api.resource import SubmissionResource
from emmet.api.routes._consumer.query_operator import (
    UserSettingsPostQuery,
    UserSettingsGetQuery,
    UserSettingsPatchQuery,
)
from emmet.core._user_settings import UserSettingsDoc


def settings_resource(consumer_settings_store):
    resource = SubmissionResource(
        consumer_settings_store,
        UserSettingsDoc,
        post_query_operators=[UserSettingsPostQuery()],
        get_query_operators=[UserSettingsGetQuery()],
        patch_query_operators=[UserSettingsPatchQuery()],
        enable_default_search=False,
        include_in_schema=False,
    )

    return resource
