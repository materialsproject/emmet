from typing import Any, Optional, Dict
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class RedoxPotentialQuery(QueryOperator):
    """
    Method to generate a query on redox potentials.
    """

    def query(
        self,
        min_reduction_potential: Optional[float] = Query(
            None, description="Minimum reduction potential."
        ),
        max_reduction_potential: Optional[float] = Query(
            None, description="Maximum reduction potential."
        ),
        min_oxidation_potential: Optional[float] = Query(
            None, description="Minimum oxidation potential."
        ),
        max_oxidation_potential: Optional[float] = Query(
            None, description="Maximum oxidation potential."
        ),
    ) -> STORE_PARAMS:
        crit: Dict[str, Any] = dict()  # type: ignore

        d = {
            "oxidation_potential": [min_oxidation_potential, max_oxidation_potential],
            "reduction_potential": [min_reduction_potential, max_reduction_potential],
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
