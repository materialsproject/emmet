import types
import typing
from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from types import UnionType
from typing import Any, ForwardRef, _eval_type, _UnionGenericAlias

import typing_extensions
from monty.json import MSONable
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.types import ImportString

import emmet.core.serialization_adapters
from emmet.core.utils import jsanitize

try:
    import pyarrow as pa
except ImportError:
    raise ImportError("Install pyarrow to get arrow representations of emmet classes")


RED = "\033[31m"
BLUE = "\033[34m"
RESET = "\033[0m"

PY_PRIMITIVES_TO_ARROW = {
    int: pa.int64(),
    float: pa.float64(),
    str: pa.string(),
    bool: pa.bool_(),
    datetime: pa.timestamp("us"),
}


def remove_empty_keys(d):
    for k, v in list(d.items()):
        if isinstance(v, dict):
            remove_empty_keys(v)
        elif v is None:
            del d[k]
        elif isinstance(v, list):
            for entry in v:
                if isinstance(entry, dict):
                    remove_empty_keys(entry)

    return d


def cleanup_msonables(d):
    return {
        k: remove_empty_keys(v) if isinstance(v, dict) and "@class" in v else v
        for k, v in jsanitize(d, allow_bson=True).items()
    }


def arrowize(obj):
    assert obj not in (
        list,
        tuple,
        set,
        dict,
        typing.Dict,
        typing.List,
        typing.Set,
        typing.Tuple,
    ), f"Cannot construct arrow type from container of type {RED}{obj}{RESET} without typed arguments"

    assert (
        obj is not Any
    ), f"Cannot infer arrow type from: {RED}{obj}{RESET}, ambiguous ({BLUE}Any{RESET}) values cannot be resolved"

    if obj in PY_PRIMITIVES_TO_ARROW:
        return PY_PRIMITIVES_TO_ARROW[obj]

    if typing.get_origin(obj) in (list, tuple, set):
        args = obj.__args__
        if len(args) == 1:
            return pa.list_(arrowize(args[0]))

        if all([member == args[0] for member in args]):
            return pa.list_(arrowize(args[0]), len(args))

        return pa.dense_union(
            [
                pa.field(f"child_{idx}", arrowize(field))
                for idx, field, in zip(range(len(args)), args)
            ]
        )

    if typing.get_origin(obj) in (Mapping, dict):
        args = typing.get_args(obj)
        key_type = arrowize(args[0])

        assert not isinstance(
            key_type, pa.UnionType
        ), f"""
        Cannot construct arrow map type from: {RED}{obj}{RESET}.
        Keys for maps must resolve to single primitive data type,
        not pyarrow UnionType: {BLUE}{key_type}{RESET}
        """

        return pa.map_(key_type, arrowize(args[1]))

    if typing.get_origin(obj) is typing.Literal:
        args = obj.__args__
        first_type = type(args[0])

        assert all(
            isinstance(member, first_type) for member in args
        ), f"Cannot infer arrow compatible primitive from literal with mixed types: {RED}{obj}{RESET}"

        return PY_PRIMITIVES_TO_ARROW[first_type]

    if isinstance(obj, type) and issubclass(obj, Enum):
        # making an assumption here based on knowledge of emmet + pymatgen classes...
        # should have better way to handle all enums to get serialized representations
        return PY_PRIMITIVES_TO_ARROW[str]

    if isinstance(obj, _UnionGenericAlias | UnionType):
        arrow_types = [
            arrowize(arg)
            for arg in list(
                filter(
                    lambda x: x is not types.NoneType,
                    obj.__args__,
                )
            )
        ]

        if all(arg == arrow_types[0] for arg in arrow_types):
            return arrow_types[0]

        return pa.dense_union(
            [
                pa.field(f"child_{idx}", field)
                for idx, field, in zip(range(len(arrow_types)), arrow_types)
            ]
        )

    if isinstance(obj, ModelMetaclass):
        return pa.struct(
            [
                pa.field(field_name, arrowize(value.annotation))
                for field_name, value in obj.model_fields.items()
            ]
        )

    if obj is ImportString:
        return PY_PRIMITIVES_TO_ARROW[str]

    if isinstance(obj, typing._TypedDictMeta | typing_extensions._TypedDictMeta):
        return pa.struct(
            [
                pa.field(field_name, arrowize(value))
                for field_name, value in obj.__annotations__.items()
            ]
        )

    if isinstance(obj, ForwardRef):
        return arrowize(obj._evaluate(globals(), locals(), frozenset()))

    if issubclass(obj, MSONable):
        assert hasattr(
            obj, "__pydantic_model__"
        ), f"No pydantic serialization adapter is specified for msonable obj: {RED}{obj}{RESET}"

        return arrowize(obj.__pydantic_model__.model_fields["root"].annotation)

    if isinstance(obj, type):
        return arrowize(
            next(
                filter(
                    lambda primitive: issubclass(obj, primitive), PY_PRIMITIVES_TO_ARROW
                )
            )
        )
