from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Path
from maggma.api.query_operator import QueryOperator

if TYPE_CHECKING:
    from emmet.core.mpid import MPID
    from maggma.api.utils import STORE_PARAMS


class PhononImgQuery(QueryOperator):
    """Method to generate a query on phonon image data."""

    def query(
        self,
        task_id: MPID = Path(
            ...,
            description="The calculation (task) ID associated with the data object",
        ),
    ) -> STORE_PARAMS:
        return {"criteria": {"task_id": str(task_id)}}
