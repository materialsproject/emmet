from emmet.api.query_operator import (
    AtlasPaginationQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource, SearchResource

from emmet.api.routes.materials.tasks.query_operators import (
    AtlasElementsQuery,
    AtlasFormulaQuery,
    DeprecationQuery,
    MultipleTaskIDsQuery,
    TrajectoryQuery,
    EntryQuery,
    LastUpdatedQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.core.tasks import DeprecationDoc, TaskDoc, TrajectoryDoc, EntryDoc

timeout = MAPISettings().TIMEOUT


def task_resource(task_store):
    resource = SearchResource(
        task_store,
        TaskDoc,
        query_operators=[
            # BatchIdQuery(field="batch_id"),
            AtlasFormulaQuery(),
            # ChemsysQuery(),
            AtlasElementsQuery(),
            MultipleTaskIDsQuery(),
            LastUpdatedQuery(),
            AtlasPaginationQuery(),
            SparseFieldsQuery(
                TaskDoc,
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


def task_deprecation_resource(materials_store):
    resource = ReadOnlyResource(
        materials_store,
        DeprecationDoc,
        query_operators=[DeprecationQuery(), PaginationQuery()],
        tags=["Materials Tasks"],
        enable_default_search=True,
        sub_path="/tasks/deprecation/",
        header_processor=GlobalHeaderProcessor(),
        timeout=timeout,
    )

    return resource


def trajectory_resource(task_store):
    resource = ReadOnlyResource(
        task_store,
        TrajectoryDoc,
        query_operators=[TrajectoryQuery(), PaginationQuery()],
        key_fields=["task_id", "calcs_reversed"],
        tags=["Materials Tasks"],
        sub_path="/tasks/trajectory/",
        header_processor=GlobalHeaderProcessor(),
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
