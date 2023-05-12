from collections import defaultdict
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
            None,
            description="A comma delimited string list of unique (cationic) species in IUCR format.",
        ),
        chemenv_iupac: Optional[str] = Query(
            None,
            description="A comma delimited string list of unique (cationic) species in IUPAC format.",
        ),
        chemenv_name: Optional[str] = Query(
            None,
            description="A comma delimited string list of coordination environment descriptions for "
            "unique (cationic) species.",
        ),
        chemenv_symbol: Optional[str] = Query(
            None,
            description="A comma delimited string list of ChemEnv symbols for unique (cationic) species "
            "in the structure.",
        ),
        species: Optional[str] = Query(
            None,
            description="A comma delimited string list of unique (cationic) species in the structure.",
        ),
        csm_min: Optional[float] = Query(
            None,
            description="Minimum value of the continous symmetry measure for any site.",
        ),
        csm_max: Optional[float] = Query(
            None,
            description="Maximum value of the continous symmetry measure for any site.",
        ),
    ) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        d = {"csm": [csm_min, csm_max]}

        for entry in d:
            if d[entry][0] is not None:
                crit[entry]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[entry]["$lte"] = d[entry][1]

        if chemenv_iucr:
            crit.update(
                {
                    "chemenv_iucr": {
                        "$in": [entry.strip() for entry in chemenv_iucr.split(",")]
                    }
                }
            )

        if chemenv_iupac:
            crit.update(
                {
                    "chemenv_iupac": {
                        "$in": [entry.strip() for entry in chemenv_iupac.split(",")]
                    }
                }
            )

        if chemenv_name:
            crit.update(
                {
                    "chemenv_name": {
                        "$in": [entry.strip() for entry in chemenv_name.split(",")]
                    }
                }
            )

        if chemenv_symbol:
            crit.update(
                {
                    "chemenv_symbol": {
                        "$in": [entry.strip() for entry in chemenv_symbol.split(",")]
                    }
                }
            )

        if species:
            crit.update(
                {"species": {"$in": [entry.strip() for entry in species.split(",")]}}
            )

        return {"criteria": crit}
