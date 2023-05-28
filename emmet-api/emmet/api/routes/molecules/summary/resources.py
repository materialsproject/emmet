from emmet.core.molecules.summary import MoleculeSummaryDoc

from maggma.api.query_operator import (
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
    NumericQuery,
)
from maggma.api.resource import ReadOnlyResource
from emmet.api.routes.molecules.molecules.query_operators import (
    FormulaQuery,
    ChemsysQuery,
    ElementsQuery,
    ChargeSpinQuery,
    DeprecationQuery,
)
from emmet.api.routes.materials.summary.query_operators import HasPropsQuery
from emmet.api.routes.molecules.summary.hint_scheme import SummaryHintScheme
from emmet.api.routes.molecules.summary.query_operators import MPculeIDsSearchQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings

timeout = MAPISettings().TIMEOUT


def summary_resource(summary_store):
    resource = ReadOnlyResource(
        summary_store,
        MoleculeSummaryDoc,
        query_operators=[
            MPculeIDsSearchQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            HasPropsQuery(),
            ChargeSpinQuery(),
            DeprecationQuery(),
            SortQuery(),
            PaginationQuery(),
            NumericQuery(
                model=MoleculeSummaryDoc,
                fields=[
                    "nelements",
                    "ionization_energy",
                    "electron_affinity",
                    "reduction_free_energy",
                    "oxidation_free_energy",
                ],
            ),
            SparseFieldsQuery(MoleculeSummaryDoc, default_fields=["molecule_id"]),
        ],
        hint_scheme=SummaryHintScheme(),
        header_processor=GlobalHeaderProcessor(),
        tags=["Molecules Summary"],
        sub_path="/summary/",
        disable_validation=True,
        timeout=timeout,
    )

    return resource
