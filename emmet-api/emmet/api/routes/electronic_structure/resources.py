from maggma.api.query_operator.dynamic import NumericQuery
from maggma.api.resource import ReadOnlyResource
from emmet.core.electronic_structure import ElectronicStructureDoc
from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery

from emmet.api.routes.materials.query_operators import (
    ElementsQuery,
    FormulaQuery,
    ChemsysQuery,
    DeprecationQuery,
    MultiMaterialIDQuery
)

from emmet.api.routes.electronic_structure.query_operators import (
    ESSummaryDataQuery,
    BSDataQuery,
    DOSDataQuery,
    ObjectQuery,
)
from emmet.core.electronic_structure import BSObjectDoc, DOSObjectDoc
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings

timeout = MAPISettings().TIMEOUT


def es_resource(es_store):
    resource = ReadOnlyResource(
        es_store,
        ElectronicStructureDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            ESSummaryDataQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            NumericQuery(model=ElectronicStructureDoc),
            DeprecationQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ElectronicStructureDoc, default_fields=["material_id", "last_updated"]
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Electronic Structure"],
        disable_validation=True,
        timeout=timeout,
    )

    return resource


def bs_resource(es_store):
    resource = ReadOnlyResource(
        es_store,
        ElectronicStructureDoc,
        query_operators=[
            BSDataQuery(),
            DeprecationQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ElectronicStructureDoc,
                default_fields=["material_id", "last_updated", "bandstructure"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Electronic Structure"],
        enable_get_by_key=False,
        sub_path="/bandstructure/",
        disable_validation=True,
        timeout=timeout,
    )

    return resource


def bs_obj_resource(s3_store):
    resource = ReadOnlyResource(
        s3_store,
        BSObjectDoc,
        query_operators=[
            ObjectQuery(),
            SparseFieldsQuery(BSObjectDoc, default_fields=["task_id", "last_updated"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Electronic Structure"],
        enable_get_by_key=False,
        enable_default_search=True,
        sub_path="/bandstructure/object/",
        query_disk_use=False,
        disable_validation=True,
    )
    return resource


def dos_resource(es_store):
    resource = ReadOnlyResource(
        es_store,
        ElectronicStructureDoc,
        query_operators=[
            DOSDataQuery(),
            DeprecationQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ElectronicStructureDoc,
                default_fields=["material_id", "last_updated", "dos"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Electronic Structure"],
        enable_get_by_key=False,
        sub_path="/dos/",
        disable_validation=True,
        timeout=timeout
    )

    return resource


def dos_obj_resource(s3_store):
    resource = ReadOnlyResource(
        s3_store,
        DOSObjectDoc,
        query_operators=[
            ObjectQuery(),
            SparseFieldsQuery(DOSObjectDoc, default_fields=["task_id", "last_updated"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Electronic Structure"],
        enable_get_by_key=False,
        enable_default_search=True,
        sub_path="/dos/object/",
        query_disk_use=False,
        disable_validation=True,
    )
    return resource
