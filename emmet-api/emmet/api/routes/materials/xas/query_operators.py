from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS
from pymatgen.core.periodic_table import Element

from emmet.core.xas import Edge, Type


class XASQuery(QueryOperator):
    def query(
        self,
        edge: Edge = Query(None, title="XAS Edge"),
        spectrum_type: Type = Query(None, title="Spectrum Type"),
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
        crit = {}

        if spectrum_ids:
            crit.update(
                {
                    "spectrum_id": {
                        "$in": [
                            spectrum_id.strip()
                            for spectrum_id in spectrum_ids.split(",")
                        ]
                    }
                }
            )

        return {"criteria": crit}
