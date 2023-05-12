from maggma.api.resource import ReadOnlyResource
from emmet.core.molecules_jcesr import MoleculesDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.legacy.jcesr.query_operators import (
    MoleculeBaseQuery,
    MoleculeElementsQuery,
    MoleculeFormulaQuery,
)
from emmet.api.routes.materials.tasks.query_operators import MultipleTaskIDsQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings


def jcesr_resource(molecules_store):
    resource = ReadOnlyResource(
        molecules_store,
        MoleculesDoc,
        query_operators=[
            MoleculeBaseQuery(),
            MoleculeElementsQuery(),
            MoleculeFormulaQuery(),
            MultipleTaskIDsQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(MoleculesDoc, default_fields=["task_id"]),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["JCESR Electrolyte Genome"],
        sub_path="/jcesr/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
