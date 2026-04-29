from fastapi import Query

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from emmet.core.mpid import AlphaID


class MaterialIDsSearchQuery(QueryOperator):
    """
    Query on alloy_pair documents using multiple material_id values
    """

    def query(
        self,
        material_ids: str | None = Query(
            None, description="Comma-separated list of material_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if material_ids:
            ids = [
                AlphaID(material_id.strip()).formatted
                for material_id in material_ids.split(",")
            ]

            crit.update(
                {
                    "$or": [
                        {"alloy_pair.id_a": {"$in": ids}},
                        {"alloy_pair.id_b": {"$in": ids}},
                    ]
                }
            )

        return {"criteria": crit}


class FormulaSearchQuery(QueryOperator):
    def query(
        self,
        formulae: str | None = Query(
            None, description="Comma-separated list of end-point formulas to query."
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if formulae:
            formulas = [formula.strip() for formula in formulae.split(",")]

            crit.update(
                {
                    "$or": [
                        {"alloy_pair.formula_a": {"$in": formulas}},
                        {"alloy_pair.formula_b": {"$in": formulas}},
                    ]
                }
            )

        return {"criteria": crit}
