from emmet.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.api.resource import ReadOnlyResource

from emmet.api.routes.materials.materials.query_operators import (
    ChemsysQuery,
    ElementsQuery,
    FormulaQuery,
)
from emmet.api.routes.materials.tasks.hint_scheme import TasksHintScheme
from emmet.api.routes.materials.tasks.query_operators import (
    MultipleTaskIDsQuery,
    LastUpdatedQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.core.defect import DefectTaskDoc

timeout = MAPISettings().TIMEOUT


def task_resource(task_store):
    resource = ReadOnlyResource(
        task_store,
        DefectTaskDoc,
        query_operators=[
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            MultipleTaskIDsQuery(),
            LastUpdatedQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                DefectTaskDoc,
                default_fields=["task_id", "formula_pretty", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        hint_scheme=TasksHintScheme(),
        tags=["Defect Tasks"],
        sub_path="/tasks/",
        timeout=timeout,
        disable_validation=True,
    )

    return resource
