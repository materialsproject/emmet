from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    IdFormatQuery,
    MultiTaskIDQuery,
    PaginationQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.core.eos import EOSDoc
from emmet.core.types.typing import format_task_id


def eos_resource(eos_store):
    resource = ReadOnlyResource(
        eos_store,
        EOSDoc,
        query_operators=[
            MultiTaskIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(EOSDoc, default_fields=["task_id"]),
            IdFormatQuery([("task_id", format_task_id)]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials EOS"],
        sub_path="/eos/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
