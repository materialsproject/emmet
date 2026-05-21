from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Protocol

from fastapi import Query

from emmet.api.utils import STORE_PARAMS, process_identifiers, split_csv


class QueryOperator(ABC):
    """
    Base Query Operator class for defining powerful query language
    in the Materials API.
    """

    @abstractmethod
    def query(self, *args, **kwargs) -> STORE_PARAMS:
        """
        The query function that does the work for this query operator.
        """

    def meta(self) -> dict:
        """
        Returns meta data to return with the Response.
        """
        return {}

    def post_process(self, docs: list[dict], query: dict) -> list[dict]:
        """
        An optional post-processing function for the data.

        Args:
            docs: the document results to post-process
            query: the store query dict to use in post-processing
        """
        return docs


@dataclass
class BoolQuery(QueryOperator):
    """
    Generates an equality query for a boolean field.

    When the supplied flag is ``None``, no criteria are emitted (the field is
    not constrained); otherwise an exact-match predicate is built against the
    given field.

    Attributes:
        field_name: The document field to match against.

    Subclasses should override ``query`` to declare their FastAPI query
    parameters and delegate to ``_prepare_query`` to build their predicate.
    """

    field_name: str

    def _prepare_query(self, flag: bool | None) -> STORE_PARAMS:
        return {"criteria": {self.field_name: flag} if flag is not None else {}}


@dataclass
class InQuery(QueryOperator):
    """
    Generates an appropriate 'in' query from a query string.

    Attributes:
        field_name: The document field to match against.
        pre_processor: Callable that converts the raw query string into a list
            of values to match against. -> inject custom higher order func logic here
            as needed
        atlas_search: If ``True``, build an Atlas Search ``in`` predicate;
            otherwise build a standard MongoDB ``$in`` predicate.

    Subclasses should override ``query`` to declare their FastAPI query
    parameters and delegate to ``_prepare_query`` to build their predicate.
    """

    field_name: str
    pre_processor: Callable[[str], list[str]] = field(default=split_csv)
    atlas_search: bool = False

    def _prepare_query(self, query_str: str | None) -> STORE_PARAMS:
        crit: dict[str, Any] = {}

        if query_str:
            processed_ids = self.pre_processor(query_str)
            crit = (
                {"in": {"path": self.field_name, "value": processed_ids}}
                if self.atlas_search
                else {self.field_name: {"$in": processed_ids}}
            )

        return {"criteria": crit}


@dataclass
class RangeQuery(QueryOperator):
    """
    Generates a range ($gte / $lte) query across one or more numeric fields.

    Each entry in the input mapping is interpreted as
    ``field_name -> [min_value, max_value]``. Either bound may be ``None`` to
    indicate that side of the range is unbounded; if both bounds are ``None``
    the field contributes no criteria.

    Subclasses should override ``query`` to declare their FastAPI query
    parameters (typically a min/max pair per field) and delegate to
    ``_prepare_query`` to build their predicate.
    """

    def _prepare_query(self, value_dict: dict[str, list[float]]) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        for entry in value_dict:
            if value_dict[entry][0] is not None:
                crit[entry]["$gte"] = value_dict[entry][0]

            if value_dict[entry][1] is not None:
                crit[entry]["$lte"] = value_dict[entry][1]

        return {"criteria": crit}


@dataclass
class DeprecationQuery(BoolQuery):
    """
    Method to generate a deprecation state query
    """

    field_name: str = "deprecated"

    def query(
        self,
        deprecated: bool | None = Query(
            False,
            description="Whether the material is marked as deprecated",
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(deprecated)


@dataclass
class MultiTaskIDQuery(InQuery):
    """Generate a query for different task_ids."""

    field_name: str = "task_id"
    pre_processor: Callable[[str], list[str]] = field(
        default=partial(process_identifiers, use_prefix=False)
    )

    def query(
        self,
        task_ids: str | None = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(task_ids)


@dataclass
class MultiMaterialIDQuery(InQuery):
    """
    Method to generate a query for different root-level material_id values
    """

    field_name: str = "material_id"
    pre_processor: Callable[[str], list[str]] = field(default=process_identifiers)

    def query(
        self,
        material_ids: str | None = Query(
            None, description="Comma-separated list of material_id values to query on"
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(material_ids)


# Allowed values for the optional ``id_format`` query parameter. Anything not
# in this set is treated as if the parameter was absent (no-op reformatting),
# which is the safer default for backwards compatibility.
_ID_FORMAT_VALUES = ("legacy", "alpha")


class IdFormatter(Protocol):
    """Callable signature for the formatters consumed by :class:`IdFormatQuery`.

    Each registered formatter is invoked as
    ``formatter(value, legacy=<bool>)`` against every truthy id-field value
    on the response. ``legacy`` is passed by keyword to match the explicit
    signatures of the canonical formatters in :mod:`emmet.core.types.typing`
    and :mod:`emmet.core.xas`.
    """

    def __call__(self, value: Any, *, legacy: bool) -> str: ...


@dataclass
class IdFormatQuery(QueryOperator):
    """Optional response-side reformatting of MP identifier fields.

    Adds an ``id_format`` query parameter to an endpoint and, on
    ``post_process``, rewrites the identifier fields on each returned
    document according to the requested shape:

    - ``id_format=legacy`` -> ``mp-149`` / ``mp-2658_Al`` / ``mp-779827-XANES-O-K``
    - ``id_format=alpha``  -> ``mp-aaaaaaft`` / ``mp-aaaaadyg_Al`` / ``aaabsjpj-XANES-O-K``
    - parameter absent (or any other value) -> documents are returned with
      identifier fields exactly as the database stores them; no rewriting
      is attempted.

    This is purely a serialization concern: ``query()`` returns an empty
    criteria dict so this operator never affects which documents the
    database returns. It only mutates the response payload.

    Constructor takes a list of ``(field_name, formatter)`` tuples. Each
    formatter must be a callable with signature ``formatter(value, legacy: bool) -> str``
    and must be fault-tolerant (i.e. return the input unchanged on parse
    failure, never raise). The canonical formatters live in
    :mod:`emmet.core.types.typing` (``format_identifier``,
    ``format_compound_identifier``, ``format_task_id``) and
    :mod:`emmet.core.xas` (``format_spectrum_id``).

    Example registration:

    .. code-block:: python

        from emmet.core.types.typing import format_identifier, format_task_id
        from emmet.core.xas import format_spectrum_id

        # /materials/summary/
        IdFormatQuery(id_fields=[("material_id", format_identifier)])

        # /materials/xas/
        IdFormatQuery(id_fields=[
            ("task_id", format_task_id),
            ("spectrum_id", format_spectrum_id),
        ])

    Attributes:
        id_fields: A list of ``(field_name, formatter)`` tuples describing
            which fields on each returned document to rewrite and how.
            Fields that are absent from a given document (e.g. due to
            sparse-fields projection) are silently skipped.
    """

    id_fields: list[tuple[str, IdFormatter]] = field(default_factory=list)

    def query(
        self,
        id_format: str | None = Query(
            None,
            description=(
                "Optional. If set to 'legacy', MP identifier fields in the "
                "response are returned in the form 'mp-149'. If set to "
                "'alpha', they are returned in the padded AlphaID form "
                "'mp-aaaaaaft'. If omitted (or set to any other value), "
                "identifiers are returned in their stored form. This is a "
                "purely cosmetic transform; query inputs accept either "
                "shape regardless."
            ),
        ),
    ) -> STORE_PARAMS:
        # The store query is empty — this operator only affects response
        # serialization. The ``id_format`` value is threaded through the
        # returned ``STORE_PARAMS`` so ``post_process`` can read it back.
        return {"criteria": {}, "id_format": id_format}

    def post_process(self, docs: list[dict], query: dict) -> list[dict]:
        fmt = query.get("id_format")
        if fmt not in _ID_FORMAT_VALUES:
            # Absent / invalid value -> no-op. We deliberately do not 400
            # on a bad value: existing clients that misspell the parameter
            # continue to receive a valid response.
            return docs

        legacy = fmt == "legacy"
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            for field_name, formatter in self.id_fields:
                value = doc.get(field_name)
                if value:
                    doc[field_name] = formatter(value, legacy=legacy)
        return docs
