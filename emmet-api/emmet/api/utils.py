import base64
import inspect
from typing import (
    Any,
    Callable,
    Literal,
    Optional,
    Union,
    get_args,  # pragma: no cover
)

from bson.objectid import ObjectId
from monty.json import MSONable
from pydantic import BaseModel
from pydantic._internal._utils import lenient_issubclass
from pydantic.fields import FieldInfo

from maggma.utils import get_flat_models_from_model

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

    remainder = {k: v for query in queries for k, v in query.items() if k not in ["criteria", "properties"]}

    return {
        "criteria": criteria,
        "properties": properties if len(properties) > 0 else None,
        **remainder,
    }


def merge_atlas_querires(queries: list[STORE_PARAMS]) -> STORE_PARAMS:
    """Merge queries for atlas search, same keys, e.g. "equals", are merged into a list."""
    criteria: list[dict] = []
    facets: dict[dict] = {}
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

    remainder = {k: v for query in queries for k, v in query.items() if k not in ["criteria", "properties", "facets"]}

    return {
        "criteria": criteria,
        "properties": properties if len(properties) > 0 else None,
        "facets": facets if len(facets) > 0 else None,
        **remainder,
    }


def attach_signature(function: Callable, defaults: dict, annotations: dict):
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

    function.__signature__ = inspect.Signature(required_params + optional_params)


def api_sanitize(
    pydantic_model: BaseModel,
    fields_to_leave: Optional[Union[str, None]] = None,
    allow_dict_msonable=False,
):
    """Function to clean up pydantic models for the API by:
        1.) Making fields optional
        2.) Allowing dictionaries in-place of the objects for MSONable quantities.

    WARNING: This works in place, so it mutates the model and all sub-models

    Args:
        pydantic_model (BaseModel): Pydantic model to alter
        fields_to_leave (list[str] | None): list of strings for model fields as "model__name__.field".
            Defaults to None.
        allow_dict_msonable (bool): Whether to allow dictionaries in place of MSONable quantities.
            Defaults to False
    """
    models = [
        model for model in get_flat_models_from_model(pydantic_model) if issubclass(model, BaseModel)
    ]  # type: list[BaseModel]

    fields_to_leave = fields_to_leave or []
    fields_tuples = [f.split(".") for f in fields_to_leave]
    assert all(len(f) == 2 for f in fields_tuples)

    for model in models:
        model_fields_to_leave = {f[1] for f in fields_tuples if model.__name__ == f[0]}
        for name in model.model_fields:
            field = model.model_fields[name]
            field_type = field.annotation

            if field_type is not None and allow_dict_msonable:
                if lenient_issubclass(field_type, MSONable):
                    field_type = allow_msonable_dict(field_type)
                else:
                    for sub_type in get_args(field_type):
                        if lenient_issubclass(sub_type, MSONable):
                            allow_msonable_dict(sub_type)

            if name not in model_fields_to_leave:
                new_field = FieldInfo.from_annotated_attribute(Optional[field_type], None)
                model.model_fields[name] = new_field

        model.model_rebuild(force=True)

    return pydantic_model


def allow_msonable_dict(monty_cls: type[MSONable]):
    """
    Patch Monty to allow for dict values for MSONable.
    """

    def validate_monty(cls, v, _):
        """
        Stub validator for MSONable as a dictionary only.
        """
        if isinstance(v, cls):
            return v
        elif isinstance(v, dict):
            # Just validate the simple Monty Dict Model
            errors = []
            if v.get("@module", "") != monty_cls.__module__:
                errors.append("@module")

            if v.get("@class", "") != monty_cls.__name__:
                errors.append("@class")

            if len(errors) > 0:
                raise ValueError("Missing Monty serialization fields in dictionary: {errors}")

            return v
        else:
            raise ValueError(f"Must provide {cls.__name__} or MSONable dictionary")

    monty_cls.validate_monty_v2 = classmethod(validate_monty)

    return monty_cls


def serialization_helper(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, bytes):
        return base64.b64encode(obj).decode("utf-8")
    raise TypeError
