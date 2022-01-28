from maggma.api.resource import ReadOnlyResource

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery

from emmet.core.alloys import AlloyPairDoc, AlloySystemDoc

from mp_api.routes.alloys.query_operators import MaterialIDsSearchQuery, FormulaSearchQuery


def alloys_resource(alloys_store):
    resource = ReadOnlyResource(
        alloys_store,
        AlloyPairDoc,
        query_operators=[
            MaterialIDsSearchQuery(),
            FormulaSearchQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                 AlloyPairDoc, default_fields=["pair_id"],
            ),
        ],
        tags=["Alloys"],
        disable_validation=True,
    )

    return resource

# TODO
# def alloy_systems_resource(alloy_systems_store):
#     resource = ReadOnlyResource(
#         alloy_systems_store,
#         AlloySystemDoc,
#         query_operators=[
#             SortQuery(),
#             PaginationQuery(),
#             SparseFieldsQuery(
#                  AlloySystemDoc, default_fields=["alloy_id"],
#             ),
#         ],
#         tags=["Alloys"],
#         disable_validation=True,
#     )
#
#     return resource