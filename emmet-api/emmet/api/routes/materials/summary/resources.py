from emmet.core.summary import SummaryDoc

from emmet.api.query_operator import (
    PaginationQuery,
    SparseFieldsQuery,
    NumericQuery,
    SortQuery,
)
from emmet.api.resource import ReadOnlyResource, AggregationResource
from emmet.api.routes.materials.materials.query_operators import (
    DeprecationQuery,
    ElementsQuery,
    FormulaQuery,
    ChemsysQuery,
    SymmetryQuery,
    LicenseQuery,
    BatchIdQuery,
)
from emmet.api.routes.materials.oxidation_states.query_operators import (
    PossibleOxiStateQuery,
)
from emmet.core.summary import SummaryStats
from emmet.api.routes.materials.summary.hint_scheme import SummaryHintScheme
from emmet.api.routes.materials.summary.query_operators import (
    HasPropsQuery,
    MaterialIDsSearchQuery,
    SearchIsStableQuery,
    SearchIsTheoreticalQuery,
    SearchMagneticQuery,
    SearchHasReconstructedQuery,
    SearchStatsQuery,
    SearchESQuery,
)
from emmet.api.routes.materials.elasticity.query_operators import (
    BulkModulusQuery,
    ShearModulusQuery,
)

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings

settings = MAPISettings()  # type: ignore
timeout = settings.TIMEOUT
sort_fields = settings.SORT_FIELDS


def summary_resource(summary_store):
    resource = ReadOnlyResource(
        summary_store,
        SummaryDoc,
        query_operators=[
            MaterialIDsSearchQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            PossibleOxiStateQuery(),
            SymmetryQuery(),
            SearchIsStableQuery(),
            SearchIsTheoreticalQuery(),
            SearchMagneticQuery(),
            SearchESQuery(),
            NumericQuery(model=SummaryDoc, excluded_fields=["composition"]),
            BulkModulusQuery(),
            ShearModulusQuery(),
            SearchHasReconstructedQuery(),
            HasPropsQuery(),
            DeprecationQuery(),
            PaginationQuery(),
            SparseFieldsQuery(SummaryDoc, default_fields=["material_id"]),
            LicenseQuery(),
            SortQuery(fields=sort_fields, max_num=1),
            BatchIdQuery(),
        ],
        hint_scheme=SummaryHintScheme(),
        header_processor=GlobalHeaderProcessor(),
        query_to_configure_on_request=LicenseQuery(),
        tags=["Materials Summary"],
        sub_path="/summary/",
        disable_validation=True,
        timeout=timeout,
    )

    return resource


def summary_stats_resource(summary_store):
    resource = AggregationResource(
        summary_store,
        SummaryStats,
        pipeline_query_operator=SearchStatsQuery(SummaryDoc),
        tags=["Materials Summary"],
        sub_path="/summary/stats/",
        header_processor=GlobalHeaderProcessor(),
        timeout=timeout,
    )

    return resource
