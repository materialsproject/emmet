from collections import defaultdict
from dataclasses import dataclass

from fastapi import Query

from emmet.api.query_operator import QueryOperator, RangeQuery
from emmet.api.utils import STORE_PARAMS


class SubstrateStructureQuery(QueryOperator):
    """
    Method to generate a query for film and substrate data.
    """

    def query(
        self,
        film_orientation: str | None = Query(
            None,
            description="Comma separated integers defining the film surface orientation.",
        ),
        substrate_orientation: str | None = Query(
            None,
            description="Comma separated integers defining the substrate surface orientation.",
        ),
    ) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        if film_orientation:
            crit["film_orient"] = " ".join(
                [entry.strip() for entry in film_orientation.split(",")]
            )

        if substrate_orientation:
            crit["orient"] = " ".join(
                [entry.strip() for entry in substrate_orientation.split(",")]
            )

        return {"criteria": crit}


@dataclass
class EnergyAreaQuery(RangeQuery):
    """
    Method to generate a query for ranges of substrate
    elastic energies and minimum coincident areas.
    """

    def query(
        self,
        area_max: float | None = Query(
            None,
            description="Maximum value for the minimum coincident interface area in Å².",
        ),
        area_min: float | None = Query(
            None,
            description="Minimum value for the minimum coincident interface area in Å².",
        ),
        energy_max: float | None = Query(
            None,
            description="Maximum value for the energy in meV.",
        ),
        energy_min: float | None = Query(
            None,
            description="Minimum value for the energy in meV.",
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(
            value_dict={
                "area": [area_min, area_max],
                "energy": [energy_min, energy_max],
            }
        )
