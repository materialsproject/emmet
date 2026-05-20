from dataclasses import dataclass

from fastapi import Query

from emmet.api.query_operator import RangeQuery
from emmet.api.utils import STORE_PARAMS


@dataclass
class PiezoelectricQuery(RangeQuery):
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
        return self._prepare_query(
            value_dict={"e_ij_max": [piezo_modulus_min, piezo_modulus_max]}
        )
