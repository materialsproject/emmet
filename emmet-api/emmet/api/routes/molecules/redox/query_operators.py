from typing import Any

from fastapi import Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class RedoxPotentialQuery(QueryOperator):
    """
    Method to generate a query on redox potentials.
    """

    def query(
        self,
        reduction_potential_min: float | None = Query(
            None, description="Minimum reduction potential."
        ),
        reduction_potential_max: float | None = Query(
            None, description="Maximum reduction potential."
        ),
        oxidation_potential_min: float | None = Query(
            None, description="Minimum oxidation potential."
        ),
        oxidation_potential_max: float | None = Query(
            None, description="Maximum oxidation potential."
        ),
    ) -> STORE_PARAMS:
        crit: dict[str, Any] = dict()  # type: ignore

        d = {
            "oxidation_potential": [oxidation_potential_min, oxidation_potential_max],
            "reduction_potential": [reduction_potential_min, reduction_potential_max],
        }

        for key in d:
            if d[key][0] is not None or d[key][1] is not None:
                crit[key] = dict()

            if d[key][0] is not None:
                crit[key]["$gte"] = d[key][0]

            if d[key][1] is not None:
                crit[key]["$lte"] = d[key][1]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("oxidation_potential", False),
            ("reduction_potential", False),
        ]
