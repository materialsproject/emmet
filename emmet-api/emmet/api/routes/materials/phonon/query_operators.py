from __future__ import annotations

from fastapi import Query

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class PhononMethodQuery(QueryOperator):
    """
    Method to query phonon method
    """

    def query(
        self,
        phonon_method: str = Query(
            None,
            description="Phonon Method to search for",
        ),
    ) -> STORE_PARAMS:
        crit = {}
        if phonon_method in {"dfpt", "phonopy", "pheasy"}:
            crit = {"phonon_method": phonon_method}

        return {"criteria": crit}
