import inspect
from abc import abstractmethod
from typing import Any, Callable

from fastapi.params import Query
from monty.json import MontyDecoder
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from emmet.core.utils import dynamic_import


class DynamicQueryOperator(QueryOperator):
    """Abstract Base class for dynamic query operators."""

    def __init__(
        self,
        model: type[BaseModel],
        fields: list[str] | None = None,
        excluded_fields: list[str] | None = None,
    ):
        self.model = model
        self.fields = fields
        self.excluded_fields = excluded_fields

        all_fields: dict[str, FieldInfo] = model.model_fields
        param_fields = fields or list(
            set(all_fields.keys()) - set(excluded_fields or [])
        )

        # Convert the fields into operator tuples
        ops = [
            op
            for name, field in all_fields.items()
            if name in param_fields
            for op in self.field_to_operator(name, field)
        ]

        # Dictionary to make converting the API query names to function that generates
        # Maggma criteria dictionaries
        self.mapping = {op[0]: op[3] for op in ops}

        def query(**kwargs) -> STORE_PARAMS:
            criteria = []
            for k, v in kwargs.items():
                if v is not None:
                    try:
                        criteria.append(self.mapping[k](v))
                    except KeyError:
                        raise KeyError(
                            f"Cannot find key {k} in current query to database mapping"
                        )

            final_crit = {}
            for entry in criteria:
                for key, value in entry.items():
                    if key not in final_crit:
                        final_crit[key] = value
                    else:
                        final_crit[key].update(value)

            return {"criteria": final_crit}

        # building the signatures for FastAPI Swagger UI
        signatures: list = [
            inspect.Parameter(
                op[0],
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=op[2],
                annotation=op[1],
            )
            for op in ops
        ]

        query.__signature__ = inspect.Signature(signatures)  # type: ignore

        self.query = query  # type: ignore

    def query(self):
        """Stub query function for abstract class."""

    @abstractmethod
    def field_to_operator(
        self, name: str, field: FieldInfo
    ) -> list[tuple[str, Any, Query, Callable[..., dict]]]:
        """
        Converts a PyDantic FieldInfo into a Tuple with the
            - query param name,
            - query param type
            - FastAPI Query object,
            - and callable to convert the value into a query dict.
        """

    @classmethod
    def from_dict(cls, d):
        if isinstance(d["model"], str):
            d["model"] = dynamic_import(d["model"])

        decoder = MontyDecoder()
        return cls(**{k: decoder.process_decoded(v) for k, v in d.items()})

    def as_dict(self) -> dict:
        """
        Special as_dict implemented to convert pydantic models into strings.
        """
        d = super().as_dict()  # Ensures sub-classes serialize correctly
        d["model"] = f"{self.model.__module__}.{self.model.__name__}"  # type: ignore
        return d


class NumericQuery(DynamicQueryOperator):
    """Query Operator to enable searching on numeric fields."""

    def field_to_operator(
        self, name: str, field: FieldInfo
    ) -> list[tuple[str, Any, Query, Callable[..., dict]]]:
        """
        Converts a PyDantic FieldInfo into a Tuple with the
        query_param name,
        default value,
        Query object,
        and callable to convert it into a query dict.
        """
        ops = []
        field_type = field.annotation

        if field_type in [int, float, float | None, int | None]:
            title: str = name or field.alias  # type: ignore

            ops = [
                (
                    f"{title}_max",
                    field_type,
                    Query(
                        default=None,
                        description=f"Query for maximum value of {title}",
                    ),
                    lambda val: {f"{title}": {"$lte": val}},
                ),
                (
                    f"{title}_min",
                    field_type,
                    Query(
                        default=None,
                        description=f"Query for minimum value of {title}",
                    ),
                    lambda val: {f"{title}": {"$gte": val}},
                ),
            ]

        if field_type in [int, int | None]:
            ops.extend(
                [
                    (
                        f"{title}",
                        field_type,
                        Query(
                            default=None,
                            description=f"Query for {title} being equal to an exact value",
                        ),
                        lambda val: {f"{title}": val},
                    ),
                    (
                        f"{title}_not_eq",
                        field_type,
                        Query(
                            default=None,
                            description=f"Query for {title} being not equal to an exact value",
                        ),
                        lambda val: {f"{title}": {"$ne": val}},
                    ),
                    (
                        f"{title}_eq_any",
                        str,  # type: ignore
                        Query(
                            default=None,
                            description=f"Query for {title} being any of these values. Provide a comma separated list.",
                        ),
                        lambda val: {
                            f"{title}": {
                                "$in": [int(entry.strip()) for entry in val.split(",")]
                            }
                        },
                    ),
                    (
                        f"{title}_neq_any",
                        str,  # type: ignore
                        Query(
                            default=None,
                            description=f"Query for {title} being not any of these values. \
                            Provide a comma separated list.",
                        ),
                        lambda val: {
                            f"{title}": {
                                "$nin": [int(entry.strip()) for entry in val.split(",")]
                            }
                        },
                    ),
                ]
            )

        return ops


class StringQueryOperator(DynamicQueryOperator):
    """Query Operator to enable searching on numeric fields."""

    def field_to_operator(
        self, name: str, field: FieldInfo
    ) -> list[tuple[str, Any, Query, Callable[..., dict]]]:
        """
        Converts a PyDantic FieldInfo into a Tuple with the
        query_param name,
        default value,
        Query object,
        and callable to convert it into a query dict.
        """
        ops = []
        field_type: type = field.annotation  # type: ignore

        if field_type in [str, str | None]:
            title: str = name

            ops = [
                (
                    f"{title}",
                    field_type,
                    Query(
                        default=None,
                        description=f"Query for {title} being equal to a value",
                    ),
                    lambda val: {f"{title}": val},
                ),
                (
                    f"{title}_not_eq",
                    field_type,
                    Query(
                        default=None,
                        description=f"Query for {title} being not equal to a value",
                    ),
                    lambda val: {f"{title}": {"$ne": val}},
                ),
                (
                    f"{title}_eq_any",
                    str,  # type: ignore
                    Query(
                        default=None,
                        description=f"Query for {title} being any of these values. Provide a comma separated list.",
                    ),
                    lambda val: {
                        f"{title}": {"$in": [entry.strip() for entry in val.split(",")]}
                    },
                ),
                (
                    f"{title}_neq_any",
                    str,  # type: ignore
                    Query(
                        default=None,
                        description=f"Query for {title} being not any of these values. Provide a comma separated list",
                    ),
                    lambda val: {
                        f"{title}": {
                            "$nin": [entry.strip() for entry in val.split(",")]
                        }
                    },
                ),
            ]

        return ops
