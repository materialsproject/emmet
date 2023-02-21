from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource

from emmet.api.routes.mpcules.molecules.query_operators import (
    ChemsysQuery,
    ElementsQuery,
    FormulaQuery,
)
from emmet.api.routes.mpcules.tasks.hint_scheme import TasksHintScheme
from emmet.api.routes.mpcules.tasks.query_operators import (
    DeprecationQuery,
    MultipleTaskIDsQuery,
    # TODO:
    # TrajectoryQuery,
    # EntryQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.core.tasks import DeprecationDoc
from emmet.core.qchem.task import TaskDoc

timeout = MAPISettings().TIMEOUT


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
                TaskDoc,
                default_fields=["task_id", "formula_alphabetical", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        hint_scheme=TasksHintScheme(),
        tags=["Tasks"],
        timeout=timeout,
        disable_validation=True,
    )

    return resource


def task_deprecation_resource(molecules_store):
    resource = ReadOnlyResource(
        molecules,
        DeprecationDoc,
        query_operators=[DeprecationQuery(), PaginationQuery()],
        tags=["Tasks"],
        enable_get_by_key=False,
        enable_default_search=True,
        sub_path="/deprecation/",
        header_processor=GlobalHeaderProcessor(),
        timeout=timeout,
    )

    return resource


# TODO: def trajectory_resource(task_store):
# TODO: def entries_resource(task_store):
