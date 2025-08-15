from fastapi import Query
from emmet.core.mpid import MPID

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS

from fastapi import Path


class PhononImgQuery(QueryOperator):
    """
    Method to generate a query on phonon image data.
    """

    def query(
        self,
        task_id: MPID = Path(
            ...,
            description="The calculation (task) ID associated with the data object",
        ),
    ) -> STORE_PARAMS:
        return {"criteria": {"task_id": str(task_id)}}


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
