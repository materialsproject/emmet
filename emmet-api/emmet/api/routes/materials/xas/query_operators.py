from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query
from pymatgen.core.periodic_table import Element

from emmet.api.query_operator import QueryOperator
from emmet.api.query_operator.identifier import CompoundIDQuery
from emmet.api.utils import STORE_PARAMS
from emmet.core.types.typing import CompoundIDType
from emmet.core.xas import XasEdge, XasType, validate_xas_spectrum_id


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


@dataclass
class XASIDQuery(CompoundIDQuery):
    """
    Method to generate a query for XAS data given a list of spectrum_ids
    """

    field_name: str = "spectrum_id"
    identifier_fields: tuple[str, ...] = (
        "task_id",
        "spectrum_type",
        "absorbing_element",
        "edge",
    )

    @staticmethod
    def validate_identifer(idx: str) -> CompoundIDType:
        """Validate an XAS spectrum ID string."""
        return validate_xas_spectrum_id(idx, as_components=True)
