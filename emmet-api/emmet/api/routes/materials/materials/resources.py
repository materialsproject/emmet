from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.materials.hint_scheme import MaterialsHintScheme
from emmet.api.routes.materials.materials.query_operators import (
    ChemsysQuery,
    DeprecationQuery,
    ElementsQuery,
    FindStructureQuery,
    FormulaAutoCompleteQuery,
    FormulaQuery,
    MultiMaterialIDQuery,
    MultiTaskIDQuery,
    SymmetryQuery,
)
from emmet.core.find_structure import FindStructure
from emmet.core.formula_autocomplete import FormulaAutocomplete
from emmet.core.vasp.material import MaterialsDoc
from maggma.api.query_operator import (
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from maggma.api.resource.aggregation import AggregationResource
from maggma.api.resource.post_resource import PostOnlyResource
from maggma.api.resource.read_resource import ReadOnlyResource

timeout = MAPISettings().TIMEOUT


def find_structure_resource(materials_store):
    resource = PostOnlyResource(
        materials_store,
        FindStructure,
        key_fields=["structure", "task_id"],
        query_operators=[FindStructureQuery()],
        tags=["Materials"],
        sub_path="/core/find_structure/",
        timeout=timeout,
    )

    return resource


def formula_autocomplete_resource(formula_autocomplete_store):
    resource = AggregationResource(
        formula_autocomplete_store,
        FormulaAutocomplete,
        pipeline_query_operator=FormulaAutoCompleteQuery(),
        tags=["Materials"],
        sub_path="/core/formula_autocomplete/",
        header_processor=GlobalHeaderProcessor(),
        timeout=timeout,
    )

    return resource


def materials_resource(materials_store):
    resource = ReadOnlyResource(
        materials_store,
        MaterialsDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            MultiTaskIDQuery(),
            SymmetryQuery(),
            DeprecationQuery(),
            NumericQuery(model=MaterialsDoc),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                MaterialsDoc,
                default_fields=["material_id", "formula_pretty", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        hint_scheme=MaterialsHintScheme(),
        tags=["Materials"],
        sub_path="/core/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
