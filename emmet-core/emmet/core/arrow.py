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

    if obj in PY_PRIMITIVES_TO_ARROW:
        return PY_PRIMITIVES_TO_ARROW[obj]

    if typing.get_origin(obj) in (list, tuple, set):
        args = obj.__args__
        if len(args) == 1:
            return pa.list_(arrowize(args[0]))

        for member in args:
            assert (
                member is args[0]
            ), f"Cannot construct arrow array from from list with mixed types: {RED}{args}{RESET}"

        return pa.list_(arrowize(args[0]), len(args))

    if typing.get_origin(obj) in (Mapping, dict):
        args = typing.get_args(obj)

        assert args[1] is not Any and not isinstance(
            args[1], UnionType | _UnionGenericAlias
        ), f"Cannot construct arrow map type from: {RED}{obj}{RESET}, mixed ({BLUE}Unions{RESET}) or ambiguous ({BLUE}Any{RESET}) values cannot be resolved"

        key_type = arrowize(args[0])
        return pa.map_(key_type, arrowize(args[1]))

    if typing.get_origin(obj) is typing.Literal:
        args = obj.__args__
        first_type = type(args[0])

        assert all(
            type(member) is first_type for member in args
        ), f"Cannot infer arrow compatible primitive from literal with mixed types: {RED}{obj}{RESET}"

        return PY_PRIMITIVES_TO_ARROW[first_type]

    if isinstance(obj, type) and issubclass(obj, Enum):
        # making an assumption here based on knowledge of emmet + pymatgen classes...
        # should have better way to handle all enums to get serialized representations
        return PY_PRIMITIVES_TO_ARROW[str]

    if isinstance(obj, _UnionGenericAlias | UnionType):
        primitives = [
            arrowize(arg)
            for arg in list(
                filter(
                    lambda x: x is not types.NoneType,
                    obj.__args__,
                )
            )
        ]

        assert all(
            arg == primitives[0] for arg in primitives
        ), f"Cannot construct arrow type from mixed union type: {RED}{obj}{RESET}. Resolves to: {BLUE}{primitives}{RESET}"

        return primitives[0]

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
