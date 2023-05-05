from typing import Optional
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class MaterialIDsSearchQuery(QueryOperator):
    """
    Method to generate a query on search docs using multiple material_id values
    """

    def query(
        self,
        material_ids: Optional[str] = Query(None, description="Comma-separated list of material_ids to query on"),
    ) -> STORE_PARAMS:

        crit = {}

        if material_ids:

            terminal_search = {"_search.id": {"$in": [material_id.strip() for material_id in material_ids.split(",")]}}

            member_search = {
                "_search.member_ids": {"$in": [material_id.strip() for material_id in material_ids.split(",")]}
            }

            crit.update({"$or": [terminal_search, member_search]})

        return {"criteria": crit}


class FormulaSearchQuery(QueryOperator):
    def query(
        self,
        formulae: Optional[str] = Query(None, description="Comma-separated list of end-point formulas to query."),
    ) -> STORE_PARAMS:

        crit = {}

        if formulae:

            formula_search = {"_search.formula": {"$in": [formula.strip() for formula in formulae.split(",")]}}

            crit.update(formula_search)

        return {"criteria": crit}
