from maggma.api.resource import ReadOnlyResource, S3URLResource
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery
from emmet.core.charge_density import ChgcarMetaDataDoc, ChgcarDataDoc
from emmet.api.routes.charge_density.query_operators import ChgcarTaskIDQuery
from emmet.api.routes.electronic_structure.query_operators import ObjectQuery


def charge_density_resource(s3_store):
    resource = ReadOnlyResource(
        s3_store,
        ChgcarMetaDataDoc,
        query_operators=[
            ChgcarTaskIDQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ChgcarMetaDataDoc, default_fields=["task_id", "last_updated", "fs_id"]
            ),
        ],
        tags=["Charge Density"],
        enable_default_search=True,
        enable_get_by_key=False,
        disable_validation=True,
    )

    return resource


def charge_density_obj_url_resource(s3_store):
    resource = S3URLResource(
        s3_store,
        url_lifetime=259200,  # 3 days
        tags=["Charge Density"],
        disable_validation=True,
        sub_path="/object/",
    )

    return resource
