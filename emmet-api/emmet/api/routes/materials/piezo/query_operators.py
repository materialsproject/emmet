from collections import defaultdict

from fastapi import Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class PiezoelectricQuery(QueryOperator):
    """
    Method to generate a query for ranges of piezoelectric data
    """

    def query(
        self,
        piezo_modulus_max: float | None = Query(
            None,
            description="Maximum value for the piezoelectric modulus in C/m².",
        ),
        piezo_modulus_min: float | None = Query(
            None,
            description="Minimum value for the piezoelectric modulus in C/m².",
        ),
    ) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        d = {
            "e_ij_max": [piezo_modulus_min, piezo_modulus_max],
        }

        for entry in d:
            if d[entry][0] is not None:
                crit[entry]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[entry]["$lte"] = d[entry][1]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("e_ij_max", False)]
