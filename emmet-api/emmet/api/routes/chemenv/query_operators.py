from typing import Optional
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class ChemEnvQuery(QueryOperator):
    """
    Method to generate a query on chemenv data
    """

    def query(
        self,
        chemenv_iucr: Optional[str] = Query(
            None, description="A comma delimited string list of unique (cationic) species in IUCR format.",
        ),
        chemenv_iupac: Optional[str] = Query(
            None, description="A comma delimited string list of unique (cationic) species in IUPAC format.",
        ),
        chemenv_name: Optional[str] = Query(
            None,
            description="A comma delimited string list of coordination environment descriptions for unique (cationic) species.",
        ),
        csm_min: Optional[int] = Query(
            None, description="Minimum value of the continous symmetry measure for any site."
        ),
        csm_max: Optional[int] = Query(
            None, description="Maximum value of the continous symmetry measure for any site."
        ),
    ) -> STORE_PARAMS:

        crit = {}  # type: dict

        if chemenv_iucr:
            crit.update({"chemenv_iucr": {"$in": [specie.strip() for specie in chemenv_iucr.split(",")]}})

        if chemenv_iupac:
            crit.update({"chemenv_iupac": {"$in": [specie.strip() for specie in chemenv_iucr.split(",")]}})

        if chemenv_name:
            crit.update({"chemenv_name": {"$in": [specie.strip() for specie in chemenv_iucr.split(",")]}})

        if csm_max is not None:
            crit.update({"csm": {"$lte": csm_max}})

        if csm_min is not None:
            crit.update({"csm": {"$gte": csm_min}})

        return {"criteria": crit}
