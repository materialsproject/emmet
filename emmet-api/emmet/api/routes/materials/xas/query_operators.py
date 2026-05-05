from __future__ import annotations

from dataclasses import dataclass
from fastapi import Query
from pymatgen.core.periodic_table import Element

from emmet.api.query_operator import QueryOperator
from emmet.api.query_operator.identifier import CompoundIDQuery
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


@dataclass
class XASIDQuery(CompoundIDQuery):
    """
    Method to generate a query for XAS data given a list of spectrum_ids
    """

    field_name: str = "spectrum_id"
    identifier_fields: tuple[str, ...] = (
        "material_id",
        "spectrum_type",
        "absorbing_element",
        "edge",
    )
    separator: str = "-"

    @staticmethod
    def process_base_identifier(identifier: str) -> str:
        """Optionally validate identifier."""
        return process_identifiers(identifier, use_prefix=False)[0]
