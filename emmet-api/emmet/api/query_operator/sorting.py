from fastapi import Query
from fastapi.exceptions import HTTPException

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class SortQuery(QueryOperator):
    """Method to generate the sorting portion of a query."""

    def __init__(self, fields: list[str] | None = None, max_num: int | None = None):
        """Sort query configuration.

        Args:
            fields (Optional[List[str]]): List of allowed fields to sort with
            max_num (Optional[int]): Max number of fields to simultaneously sort with

        """
        self.fields = fields or []
        self.max_num = max_num or 0

        if self.max_num < 0:
            raise ValueError("Max number of fields should be larger than 0")

    def query(
        self,
        _sort_fields: str | None = Query(
            None,
            description="Comma delimited fields to sort with.\
 Prefixing '-' to a field will force a sort in descending order.",
        ),
    ) -> STORE_PARAMS:
        sort = {}

        if _sort_fields:
            field_list = _sort_fields.split(",")
            if self.max_num and len(field_list) > self.max_num:
                raise HTTPException(
                    status_code=400,
                    detail=f"Please provide at most {self.max_num} field(s) to sort with",
                )

            for sort_field in field_list:
                query_entry = {sort_field: 1}

                if sort_field.startswith("-"):
                    query_entry = {sort_field[1:]: -1}
                    sort_field = sort_field[1:]

                if self.fields and sort_field not in self.fields:
                    continue

                sort.update(query_entry)

        return {"sort": sort}
