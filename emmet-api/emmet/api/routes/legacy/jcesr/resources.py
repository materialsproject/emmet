from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    MultiTaskIDQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.legacy.jcesr.query_operators import (
    MoleculeBaseQuery,
    MoleculeElementsQuery,
    MoleculeFormulaQuery,
)
from emmet.api.utils import split_csv
from emmet.core.molecules_jcesr import MoleculesDoc

JCESR_SORT_FIELDS = [
    "task_id",
    "EA",
    "IE",
    "charge",
]


def jcesr_resource(molecules_store):
    resource = ReadOnlyResource(
        molecules_store,
        MoleculesDoc,
        query_operators=[
            MoleculeBaseQuery(),
            MoleculeElementsQuery(),
            MoleculeFormulaQuery(),
            MultiTaskIDQuery(pre_processor=split_csv),
            PaginationQuery(),
            SortQuery(fields=JCESR_SORT_FIELDS, max_num=1),
            SparseFieldsQuery(MoleculesDoc, default_fields=["task_id"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["JCESR Electrolyte Genome"],
        sub_path="/jcesr/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
