from maggma.api.resource import ReadOnlyResource
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.core.charge_density import ChgcarDataDoc
from emmet.api.routes.charge_density.query_operators import ChgcarTaskIDQuery
from emmet.api.core.global_header import GlobalHeaderProcessor


def charge_density_resource(s3_store):
    resource = ReadOnlyResource(
        s3_store,
        ChgcarDataDoc,
        query_operators=[
            ChgcarTaskIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ChgcarDataDoc, default_fields=["task_id", "last_updated", "fs_id"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Charge Density"],
        enable_default_search=True,
        enable_get_by_key=False,
        disable_validation=True,
        query_disk_use=False,
    )

    return resource


def charge_density_url_resource(s3_store):
    resource = ReadOnlyResource(
        s3_store,
        ChgcarDataDoc,
        key_fields=["task_id", "fs_id", "url", "s3_url_prefix", "requested_datetime", "expiry_datetime"],
        tags=["Charge Density"],
        enable_default_search=False,
        enable_get_by_key=True,
        disable_validation=True,
    )

    return resource
