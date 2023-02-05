from typing import Optional
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class NBOPopulationQuery(QueryOperator):
    """
    Method to generate a query on NBO natural population data.
    """

    def query(
        self,
        open_shell: Optional[bool] = Query(
            False,
            description="Should the molecules have unpaired (radical) electrons?"
        ),
        min_core_electron: Optional[float] = Query(
            None,
            description="Minimum number of core electrons in an atom in this molecule."
        ),
        max_core_electron: Optional[float] = Query(
            None,
            description="Maximum number of core electrons in an atom in this molecule."
        ),
        min_valence_electron: Optional[float] = Query(
            None,
            description="Minimum number of valence electrons in an atom in this molecule."
        ),
        max_valence_electron: Optional[float] = Query(
            None,
            description="Maximum number of valence electrons in an atom in this molecule."
        ),
        min_rydberg_electron: Optional[float] = Query(
            None,
            description="Minimum number of Rydberg electrons in an atom in this molecule."
        ),
        max_rydberg_electron: Optional[float] = Query(
            None,
            description="Maximum number of Rydberg electrons in an atom in this molecule."
        ),
    ) -> STORE_PARAMS:

        crit = {"open_shell": open_shell}

        d = {
            "core_electrons": [min_core_electron, max_core_electron],
            "valence_electrons": [min_valence_electron, max_valence_electron],
            "rydberg_electrons": [min_rydberg_electron, max_rydberg_electron],
        }

        for entry in d:
            key = "nbo_population." + entry
            if d[entry][0] is not None or d[entry][1] is not None:
                crit[key] = dict()

            if d[entry][0] is not None:
                crit[key]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[key]["$lte"] = d[entry][1]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("open_shell", False),
                ("nbo_population.core_electrons", False),
                ("nbo_population.valence_electrons", False),
                ("nbo_population.rydberg_electrons", False)]


class NBOLonePairQuery(BaseQuery):
    """
    Method to generate a query on NBO lone pair data.
    """

    def query(
        self,
        open_shell: Optional[bool] = Query(
            False,
            description="Should the molecules have unpaired (radical) electrons?"
        ),
        
    ):
        pass


class NBOBondQuery(BaseQuery):
    pass


class NBOInteractionQuery(BaseQuery):
    pass