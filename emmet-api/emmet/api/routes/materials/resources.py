from maggma.api.resource.read_resource import ReadOnlyResource
from maggma.api.resource.post_resource import PostOnlyResource
from maggma.api.resource.aggregation import AggregationResource


from emmet.core.vasp.material import MaterialsDoc
from emmet.core.find_structure import FindStructure
from emmet.core.formula_autocomplete import FormulaAutocomplete

from maggma.api.query_operator import (
    PaginationQuery,
    SparseFieldsQuery,
    SortQuery,
    NumericQuery,
)

from emmet.api.routes.materials.hint_scheme import MaterialsHintScheme
from emmet.api.routes.materials.query_operators import (
    ElementsQuery,
    FormulaQuery,
    ChemsysQuery,
    DeprecationQuery,
    SymmetryQuery,
    MultiTaskIDQuery,
    FindStructureQuery,
    FormulaAutoCompleteQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor


def find_structure_resource(materials_store):
    resource = PostOnlyResource(
        materials_store,
        FindStructure,
        key_fields=["structure", "task_id"],
        query_operators=[FindStructureQuery()],
        tags=["Materials"],
        sub_path="/find_structure/",
    )

    return resource


def formula_autocomplete_resource(formula_autocomplete_store):
    resource = AggregationResource(
        formula_autocomplete_store,
        FormulaAutocomplete,
        pipeline_query_operator=FormulaAutoCompleteQuery(),
        tags=["Materials"],
        sub_path="/formula_autocomplete/",
        header_processor=GlobalHeaderProcessor(),
    )

    return resource


def materials_resource(materials_store):

    resource = ReadOnlyResource(
        materials_store,
        MaterialsDoc,
        query_operators=[
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
        disable_validation=True,
    )

    return resource
