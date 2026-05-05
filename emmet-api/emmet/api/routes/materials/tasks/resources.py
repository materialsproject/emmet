from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    AtlasPaginationQuery,
    MultiTaskIDQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource, SearchResource
from emmet.api.routes.materials.tasks.query_operators import (
    AtlasBatchIdQuery,
    AtlasElementsQuery,
    AtlasFormulaQuery,
    EntryQuery,
    LastUpdatedQuery,
)
from emmet.core.tasks import CoreTaskDoc, EntryDoc

timeout = MAPISettings().TIMEOUT


def task_resource(task_store):
    resource = SearchResource(
        task_store,
        CoreTaskDoc,
        query_operators=[
            AtlasBatchIdQuery(),
            AtlasFormulaQuery(),
            AtlasElementsQuery(),
            MultiTaskIDQuery(atlas_search=True),
            LastUpdatedQuery(),
            AtlasPaginationQuery(),
            SparseFieldsQuery(
                CoreTaskDoc,
                default_fields=["task_id", "formula_pretty", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Tasks"],
        sub_path="/tasks/",
        timeout=timeout,
        disable_validation=True,
    )

    return resource


def entries_resource(task_store):
    resource = ReadOnlyResource(
        task_store,
        EntryDoc,
        query_operators=[EntryQuery(), PaginationQuery()],
        key_fields=[
            "task_id",
            "input",
            "output",
            "run_type",
            "task_type",
            "completed_at",
            "last_updated",
        ],
        tags=["Materials Tasks"],
        sub_path="/tasks/entries/",
        header_processor=GlobalHeaderProcessor(),
        timeout=timeout,
        disable_validation=True,
    )

    return resource
