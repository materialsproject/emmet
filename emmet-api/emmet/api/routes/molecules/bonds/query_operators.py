from typing import Any

from fastapi import Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS


class BondTypeLengthQuery(QueryOperator):
    """
    Method to generate a query on bond type and length data.
    """

    def query(
        self,
        bond_type: str | None = Query(
            None, description="Bond type of interest; e.g. C-O for carbon-oxygen bonds."
        ),
        bond_length_max: float | None = Query(
            None,
            description="Maximum value for the bond lengths in the molecule.",
        ),
        bond_length_min: float | None = Query(
            None,
            description="Minimum value for the bond lengths in the molecule.",
        ),
    ) -> STORE_PARAMS:
        if bond_type is None:
            return {"criteria": dict()}

        # Clean bond_type
        elements = bond_type.split("-")
        if len(elements) != 2:
            raise ValueError(
                f"Improper bond_type given {bond_type}! Must be in form 'A-B', where A and B are element "
                "symbols!"
            )
        key = f"bond_types.{'-'.join(sorted([e.capitalize() for e in elements]))}"

        crit: dict[str, Any] = {
            key: dict()  # type: ignore
        }  # type: ignore

        if bond_length_max is not None:
            crit[key]["$lte"] = bond_length_max
        if bond_length_min is not None:
            crit[key]["$gte"] = bond_length_min

        # If no max or min, just make sure bond type exists
        if len(crit[key]) == 0:
            crit[key]["$exists"] = True

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("bond_types", False)]
