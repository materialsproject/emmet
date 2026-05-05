from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

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
