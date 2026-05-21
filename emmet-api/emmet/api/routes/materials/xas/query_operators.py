from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query
from emmet.core.io.pymatgen import Element

from emmet.api.query_operator import QueryOperator
from emmet.api.query_operator.identifier import CompoundIDQuery
from emmet.api.utils import STORE_PARAMS
from emmet.core.types.typing import CompoundIDType
from emmet.core.xas import XasEdge, XasType, validate_xas_spectrum_id

# Field names on each XASDoc-shaped response row that compose a spectrum id,
# in the order ``XASDoc.spectrum_id`` joins them (see ``emmet.core.xas``).
# Kept here so the synthesis operator and any related downstream code share
# a single source of truth for the spectrum-id shape.
_SPECTRUM_ID_COMPONENT_FIELDS: tuple[str, ...] = (
    "task_id",
    "spectrum_type",
    "absorbing_element",
    "edge",
)


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
    identifier_fields: tuple[str, ...] = _SPECTRUM_ID_COMPONENT_FIELDS

    @staticmethod
    def validate_identifer(idx: str) -> CompoundIDType:
        """Validate an XAS spectrum ID string."""
        return validate_xas_spectrum_id(idx, as_components=True)


class SpectrumIdSynthesisQuery(QueryOperator):
    """Inject the computed ``spectrum_id`` field into each XAS response doc.

    ``XASDoc.spectrum_id`` is defined as a ``@cached_property`` on the model
    (see ``emmet.core.xas``) rather than a pydantic ``Field`` or
    ``@computed_field``. This keeps the value out of the DB write path but
    also means pydantic does not include it in ``model_dump()`` or in the
    serialized API response — so consumers that ask for ``spectrum_id`` (for
    example to render a Spectrum ID column in an explorer) get nothing.

    This operator restores ``spectrum_id`` on the response by composing it
    from the four component fields (``task_id``, ``spectrum_type``,
    ``absorbing_element``, ``edge``) joined with ``-``, matching what
    ``XASDoc.spectrum_id`` would compute.

    Ordering note: this operator must run **before** ``IdFormatQuery`` in
    the resource's ``query_operators`` list. ``IdFormatQuery`` reformats
    existing fields based on the ``id_format`` query parameter; if we
    synthesize ``spectrum_id`` after that step, the resulting value's
    leading id component will not be in the user-requested shape. With the
    correct order, the synthesized value inherits whatever shape ``task_id``
    currently holds and is then reformatted along with everything else.

    No-op behavior is preserved if any required component field is missing
    from the doc (e.g. sparse-fields projection that excludes one of them),
    so the operator does not raise from a display path.
    """

    def query(self) -> STORE_PARAMS:
        # Synthesis-only operator: no query parameters, no DB criteria.
        return {"criteria": {}}

    def post_process(self, docs: list[dict], query: dict) -> list[dict]:
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if "spectrum_id" in doc and doc["spectrum_id"]:
                # An explicit value was already provided (rare, but possible
                # if the DB starts persisting it or a future code path
                # populates it). Don't clobber.
                continue
            try:
                parts = [str(doc[field]) for field in _SPECTRUM_ID_COMPONENT_FIELDS]
            except KeyError:
                # Missing one of the component fields (sparse-fields
                # projection). Skip rather than half-populate.
                continue
            doc["spectrum_id"] = "-".join(parts)
        return docs
