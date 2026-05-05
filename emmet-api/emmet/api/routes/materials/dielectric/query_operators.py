from fastapi import Query

from emmet.api.query_operator import RangeQuery
from emmet.api.utils import STORE_PARAMS


class DielectricQuery(RangeQuery):
    """
    Method to generate a query for ranges of dielectric constant data
    """

    def query(
        self,
        e_total_max: float | None = Query(
            None,
            description="Maximum value for the total dielectric constant.",
        ),
        e_total_min: float | None = Query(
            None,
            description="Minimum value for the total dielectric constant.",
        ),
        e_ionic_max: float | None = Query(
            None,
            description="Maximum value for the ionic dielectric constant.",
        ),
        e_ionic_min: float | None = Query(
            None,
            description="Minimum value for the ionic dielectric constant.",
        ),
        e_electronic_max: float | None = Query(
            None,
            description="Maximum value for the electronic dielectric constant.",
        ),
        e_electronic_min: float | None = Query(
            None,
            description="Minimum value for the electronic dielectric constant.",
        ),
        n_max: float | None = Query(
            None,
            description="Maximum value for the refractive index.",
        ),
        n_min: float | None = Query(
            None,
            description="Minimum value for the refractive index.",
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(
            value_dict={
                "e_total": [e_total_min, e_total_max],
                "e_ionic": [e_ionic_min, e_ionic_max],
                "e_electronic": [e_electronic_min, e_electronic_max],
                "n": [n_min, n_max],
            }
        )
