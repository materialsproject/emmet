"""Define utilities for emmet-api."""

from __future__ import annotations

import base64
import inspect
from typing import (
    Any,
    Literal,
    TYPE_CHECKING,
)

from bson.objectid import ObjectId

if TYPE_CHECKING:
    from collections.abc import Callable


QUERY_PARAMS = ["criteria", "properties", "skip", "limit"]
STORE_PARAMS = dict[
    Literal[
        "criteria",
        "properties",
        "sort",
        "skip",
        "limit",
        "request",
        "pipeline",
        "count_hint",
        "agg_hint",
        "update",
        "facets",
    ],
    Any,
]


def merge_queries(queries: list[STORE_PARAMS]) -> STORE_PARAMS:
    criteria: STORE_PARAMS = {}
    properties: list[str] = []
    for sub_query in queries:
        if "criteria" in sub_query:
            criteria.update(sub_query["criteria"])
        if "properties" in sub_query:
            properties.extend(sub_query["properties"])

    remainder = {
        k: v
        for query in queries
        for k, v in query.items()
        if k not in ["criteria", "properties"]
    }

    return {
        "criteria": criteria,
        "properties": properties if len(properties) > 0 else None,
        **remainder,
    }


def merge_atlas_queries(queries: list[STORE_PARAMS]) -> STORE_PARAMS:
    """Merge queries for atlas search, same keys, e.g. "equals", are merged into a list."""
    criteria: list[dict] = []
    facets: dict[Any, Any] = {}
    properties: list[str] = []
    for sub_query in queries:
        if "criteria" in sub_query:
            for k, v in sub_query["criteria"].items():
                if isinstance(v, dict):
                    # only one criteria per operator
                    criteria.append({k: v})
                elif isinstance(v, list):
                    # multiple criteria per operator
                    criteria.extend({k: i} for i in v)
        if sub_query.get("facets", False):
            facets.update(sub_query["facets"])
        if sub_query.get("properties", False):
            properties.extend(sub_query["properties"])

    remainder = {
        k: v
        for query in queries
        for k, v in query.items()
        if k not in ["criteria", "properties", "facets"]
    }

    return {
        "criteria": criteria,
        "properties": properties if len(properties) > 0 else None,
        "facets": facets if len(facets) > 0 else None,
        **remainder,
    }


def attach_signature(function: Callable, defaults: dict, annotations: dict) -> None:
    """
    Attaches signature for defaults and annotations for parameters to function.

    Args:
        function: callable function to attach the signature to
        defaults: dictionary of parameters -> default values
        annotations: dictionary of type annotations for the parameters
    """
    required_params = [
        inspect.Parameter(
            param,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=defaults.get(param),
            annotation=annotations.get(param),
        )
        for param in annotations
        if param not in defaults
    ]

    optional_params = [
        inspect.Parameter(
            param,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=defaults.get(param),
            annotation=annotations.get(param),
        )
        for param in defaults
    ]

    function.__signature__ = inspect.Signature(required_params + optional_params)  # type: ignore[attr-defined]


def serialization_helper(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, bytes):
        return base64.b64encode(obj).decode("utf-8")
    raise TypeError
