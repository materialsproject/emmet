from dataclasses import dataclass

from fastapi import Query

from emmet.api.query_operator import BoolQuery
from emmet.api.utils import STORE_PARAMS


@dataclass
class ReconstructedQuery(BoolQuery):
    """
    Method to generate a query on whether an entry or material
    contains a reconstructed surface.
    """

    field_name: str = "has_reconstructed"

    def query(
        self,
        has_reconstructed: bool | None = Query(
            None,
            description="Whether an entry or material has a reconstructed surface.",
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(has_reconstructed)
