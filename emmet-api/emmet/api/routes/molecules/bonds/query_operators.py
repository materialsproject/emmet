from typing import Any, Dict, Optional
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class BondTypeLengthQuery(QueryOperator):
    """
    Method to generate a query on bond type and length data.
    """

    def query(
        self,
        bond_type: Optional[str] = Query(
            None, description="Bond type of interest; e.g. C-O for carbon-oxygen bonds."
        ),
        max_bond_length: Optional[float] = Query(
            None,
            description="Maximum value for the bond lengths in the molecule.",
        ),
        min_bond_length: Optional[float] = Query(
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

        crit: Dict[str, Any] = {
            key: dict()  # type: ignore
        }  # type: ignore

        if max_bond_length is not None:
            crit[key]["$lte"] = max_bond_length
        if min_bond_length is not None:
            crit[key]["$gte"] = min_bond_length

        # If no max or min, just make sure bond type exists
        if len(crit[key]) == 0:
            crit[key]["$exists"] = True

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("bond_types", False)]
