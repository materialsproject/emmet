from fastapi import HTTPException, Query

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class PaginationQuery(QueryOperator):
    """Query operators to provides Pagination."""

    def __init__(self, default_limit: int = 100, max_limit: int = 1000):
        """
        Args:
            default_limit: the default number of documents to return
            max_limit: max number of documents to return.
        """
        self.default_limit = default_limit
        self.max_limit = max_limit

        def query(
            _page: int = Query(
                None,
                description="Page number to request (takes precedent over _limit and _skip).",
            ),
            _per_page: int = Query(
                default_limit,
                description="Number of entries to show per page (takes precedent over _limit and _skip)."
                f" Limited to {max_limit}.",
            ),
            _skip: int = Query(
                0,
                description="Number of entries to skip in the search.",
            ),
            _limit: int = Query(
                default_limit,
                description=f"Max number of entries to return in a single query. Limited to {max_limit}.",
            ),
        ) -> STORE_PARAMS:
            """
            Pagination parameters for the API Endpoint.
            """
            if _page is not None:
                if _per_page > max_limit:
                    raise HTTPException(
                        status_code=400,
                        detail="Requested more data per query than allowed by this endpoint."
                        f" The max limit is {max_limit} entries",
                    )

                if _page < 0 or _per_page < 0:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot request negative _page or _per_page values",
                    )

                return {
                    "skip": ((_page - 1) * _per_page) if _page >= 1 else 0,
                    "limit": _per_page,
                }

            else:
                if _limit > max_limit:
                    raise HTTPException(
                        status_code=400,
                        detail="Requested more data per query than allowed by this endpoint."
                        f" The max limit is {max_limit} entries",
                    )

                if _skip < 0 or _limit < 0:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot request negative _skip or _limit values",
                    )

                return {"skip": _skip, "limit": _limit}

        self.query = query  # type: ignore

    def query(self):
        """Stub query function for abstract class."""

    def meta(self) -> dict:
        """
        Metadata for the pagination params.
        """
        return {"max_limit": self.max_limit}
