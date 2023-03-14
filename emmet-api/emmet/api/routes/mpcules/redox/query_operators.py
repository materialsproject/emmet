from typing import Any, Optional
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class RedoxPotentialQuery(QueryOperator):
    """
    Method to generate a query on redox potentials.
    """

    def query(
        self,
        electrode: str = Query(
            "H",
            description="Reference electrode to be queried (e.g. 'H', 'Li', 'Mg')."
        ),
        min_reduction_potential: Optional[float] = Query(
            None,
            description="Minimum reduction potential using the selected reference electrode."
        ),
        max_reduction_potential: Optional[float] = Query(
            None,
            description="Maximum reduction potential using the selected reference electrode."
        ),
        min_oxidation_potential: Optional[float] = Query(
            None,
            description="Minimum oxidation potential using the selected reference electrode."
        ),
        max_oxidation_potential: Optional[float] = Query(
            None,
            description="Maximum oxidation potential using the selected reference electrode."
        ),
    ) -> STORE_PARAMS:

        crit: Dict[str, Any] = dict()  # type: ignore

        d = {
            "oxidation_potentials": [min_oxidation_potential, max_oxidation_potential],
            "reduction_potentials": [min_reduction_potential, max_reduction_potential]
        }

        for entry in d:
            key = entry + "." + electrode
            if d[entry][0] is not None or d[entry][1] is not None:
                crit[key] = dict()

            if d[entry][0] is not None:
                crit[key]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[key]["$lte"] = d[entry][1]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("oxidation_potentials", False),
            ("reduction_potentials", False),
        ]
