from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import (
    DeprecationQuery,
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.routes.materials.elasticity.query_operators import (
    BulkModulusQuery,
    ShearModulusQuery,
)
from emmet.api.routes.materials.materials.query_operators import (
    BatchIdQuery,
    ChemsysQuery,
    ElementsQuery,
    FormulaQuery,
    LicenseQuery,
    SymmetryQuery,
)
from emmet.api.routes.materials.oxidation_states.query_operators import (
    PossibleOxiStateQuery,
)
from emmet.api.routes.materials.summary.hint_scheme import SummaryHintScheme
from emmet.api.routes.materials.summary.query_operators import (
    HasPropsQuery,
    MaterialIDsSearchQuery,
    SearchESQuery,
    SearchIsStableQuery,
    SearchIsTheoreticalQuery,
    SearchMagneticQuery,
)
from emmet.api.routes.materials.surface_properties.query_operators import (
    ReconstructedQuery,
)
from emmet.core.summary import SummaryDoc

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
            ReconstructedQuery(),
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
