from maggma.api.resource.read_resource import ReadOnlyResource
from maggma.api.resource.post_resource import PostOnlyResource
from maggma.api.resource.aggregation import AggregationResource


from emmet.core.vasp.material import MaterialsDoc
from emmet.core.find_structure import FindStructure
from emmet.core.formula_autocomplete import FormulaAutocomplete

from maggma.api.query_operator import (
    PaginationQuery,
    SparseFieldsQuery,
    NumericQuery,
)

from emmet.api.routes.materials.materials.query_operators import (
    ElementsQuery,
    FormulaQuery,
    ChemsysQuery,
    DeprecationQuery,
    SymmetryQuery,
    MultiTaskIDQuery,
    FindStructureQuery,
    FormulaAutoCompleteQuery,
    MultiMaterialIDQuery,
    LicenseQuery,
    BlessedCalcsQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings

timeout = MAPISettings().TIMEOUT  # type: ignore


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


def blessed_tasks_resource(materials_store):
    resource = ReadOnlyResource(
        materials_store,
        MaterialsDoc,
        query_operators=[
            BlessedCalcsQuery(),
            MultiMaterialIDQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            MultiTaskIDQuery(),
            DeprecationQuery(),
            NumericQuery(model=MaterialsDoc),
            PaginationQuery(),
            LicenseQuery(),
            SparseFieldsQuery(
                MaterialsDoc,
                default_fields=["material_id", "last_updated"],
            ),
        ],
        key_fields=[
            "material_id",
            "chemsys",
            "formula_pretty",
            "deprecated",
            "entries",
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials"],
        sub_path="/core/blessed_tasks/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,  # type: ignore
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
            PaginationQuery(),
            SparseFieldsQuery(
                MaterialsDoc,
                default_fields=["material_id", "formula_pretty", "last_updated"],
            ),
            LicenseQuery(),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials"],
        sub_path="/core/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,  # type: ignore
    )

    return resource
