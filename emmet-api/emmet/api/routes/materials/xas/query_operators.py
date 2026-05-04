from __future__ import annotations

from fastapi import Query
from pymatgen.core.periodic_table import Element

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS, process_identifiers
from emmet.core.xas import XasEdge, XasType


class XASQuery(QueryOperator):
    def query(
        self,
        edge: XasEdge = Query(None, title="XAS Edge"),
        spectrum_type: XasType = Query(None, title="Spectrum Type"),
        absorbing_element: Element = Query(None, title="Absorbing Element"),
    ) -> STORE_PARAMS:
        """
        Query parameters unique to XAS
        """
        query = {
            "edge": edge.value if edge else None,
            "absorbing_element": str(absorbing_element) if absorbing_element else None,
            "spectrum_type": str(spectrum_type.value) if spectrum_type else None,
        }
        query = {k: v for k, v in query.items() if v}

        return {"criteria": query} if len(query) > 0 else {}

    def ensure_indexes(self):  # pragma: no cover
        keys = ["edge", "absorbing_element", "spectrum_type"]
        return [(key, False) for key in keys]


class XASIDQuery(QueryOperator):
    """
    Method to generate a query for XAS data given a list of spectrum_ids
    """

    def query(
        self,
        spectrum_ids: str | None = Query(
            None, description="Comma-separated list of spectrum_id to query on"
        ),
    ) -> STORE_PARAMS:
        crit: dict = {}

        if spectrum_ids:
            id_list = spectrum_ids.split(",")
            parsed = [_id.rsplit("-", 3) for _id in id_list]
            identifiers, spectrum_types, absorbing_elements, edges = zip(*parsed)

            identifiers = [
                process_identifiers(i, use_prefix=False)[0] for i in identifiers
            ]

            fields = {
                "material_id": identifiers,
                "spectrum_type": list(set(spectrum_types)),
                "absorbing_element": list(set(absorbing_elements)),
                "edge": list(set(edges)),
            }

            crit = {k: {"$in": v} for k, v in fields.items()}

        return {"criteria": crit}
