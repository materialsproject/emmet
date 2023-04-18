from maggma.api.resource import ReadOnlyResource
from emmet.core.fermi import FermiDoc
from emmet.api.core.global_header import GlobalHeaderProcessor
from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery


def fermi_resource(fermi_store):
    resource = ReadOnlyResource(
        fermi_store,
        FermiDoc,
        query_operators=[
            PaginationQuery(),
            SparseFieldsQuery(FermiDoc, default_fields=["task_id", "last_updated"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Electronic Structure"],
        sub_path="/fermi/",
        disable_validation=True,
    )

    return resource
