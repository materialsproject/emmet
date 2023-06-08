from __future__ import annotations

from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.mpcomplete.query_operator import (
    MPCompleteGetQuery,
    MPCompletePostQuery,
)
from emmet.core.mpcomplete import MPCompleteDataStatus, MPCompleteDoc
from maggma.api.query_operator import PaginationQuery
from maggma.api.resource import SubmissionResource


def mpcomplete_resource(mpcomplete_store):
    resource = SubmissionResource(
        mpcomplete_store,
        MPCompleteDoc,
        post_query_operators=[MPCompletePostQuery()],
        get_query_operators=[MPCompleteGetQuery(), PaginationQuery()],
        tags=["MPComplete"],
        state_enum=MPCompleteDataStatus,
        default_state=MPCompleteDataStatus.submitted.value,
        calculate_submission_id=True,
        include_in_schema=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
