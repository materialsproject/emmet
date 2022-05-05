from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource

from emmet.api.routes.materials.query_operators import (
    ChemsysQuery,
    ElementsQuery,
    FormulaQuery,
)
from emmet.api.routes.tasks.hint_scheme import TasksHintScheme
from emmet.api.routes.tasks.query_operators import (
    DeprecationQuery,
    MultipleTaskIDsQuery,
    TrajectoryQuery,
    EntryQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.core.tasks import DeprecationDoc, TaskDoc, TrajectoryDoc, EntryDoc


def task_resource(task_store):
    resource = ReadOnlyResource(
        task_store,
        TaskDoc,
        query_operators=[
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            MultipleTaskIDsQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                TaskDoc, default_fields=["task_id", "formula_pretty", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        hint_scheme=TasksHintScheme(),
        tags=["Tasks"],
    )

    return resource


def task_deprecation_resource(materials_store):
    resource = ReadOnlyResource(
        materials_store,
        DeprecationDoc,
        query_operators=[DeprecationQuery(), PaginationQuery()],
        tags=["Tasks"],
        enable_get_by_key=False,
        enable_default_search=True,
        sub_path="/deprecation/",
        header_processor=GlobalHeaderProcessor(),
    )

    return resource


def trajectory_resource(task_store):
    resource = ReadOnlyResource(
        task_store,
        TrajectoryDoc,
        query_operators=[TrajectoryQuery(), PaginationQuery()],
        key_fields=["task_id", "calcs_reversed"],
        tags=["Tasks"],
        sub_path="/trajectory/",
        header_processor=GlobalHeaderProcessor(),
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
        tags=["Tasks"],
        sub_path="/entries/",
        header_processor=GlobalHeaderProcessor(),
    )

    return resource
