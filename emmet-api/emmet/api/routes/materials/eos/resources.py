from maggma.api.query_operator.dynamic import NumericQuery
from maggma.api.resource import ReadOnlyResource
from emmet.core.eos import EOSDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings


def eos_resource(eos_store):
    resource = ReadOnlyResource(
        eos_store,
        EOSDoc,
        query_operators=[
            NumericQuery(model=EOSDoc),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(EOSDoc, default_fields=["task_id"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["EOS"],
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT
    )

    return resource
