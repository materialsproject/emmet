from maggma.api.resource import ReadOnlyResource
from emmet.core.molecules_old import MoleculesDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from emmet.api.routes.molecules.query_operators import (
    MoleculeBaseQuery,
    MoleculeElementsQuery,
    MoleculeFormulaQuery,
)
from emmet.api.routes.tasks.query_operators import MultipleTaskIDsQuery
from emmet.api.core.global_header import GlobalHeaderProcessor


def molecules_resource(molecules_store):
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
        tags=["Molecules"],
        disable_validation=True,
    )

    return resource
