import sys
import types
import typing
from typing_extensions import NotRequired
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import UnionType

import pyarrow as pa
import typing_extensions
from monty.json import MSONable
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.types import ImportString

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


# issues re: pa.UnionType (sparse and dense) implementation:
# https://github.com/apache/arrow/issues/19157
# https://github.com/apache/arrow/issues/31211
# https://github.com/apache/arrow/issues/43857

# until union (de)serialization is supported on the pyarrow side we
# strictly must narrow all union types in emmet to a single type, e.g.,
#   my_list_of_numbers: list[int | float | None] = pydantic.Field(...)
# won't fly


def arrowize(obj) -> pa.DataType:
    """
    Converts Python type annotations to PyArrow data types.

    Recursively introspects type annotations and constructs corresponding
    PyArrow data types. This enables schema generation for Arrow-based
    serialization but does not guarantee successful serialization.

    Supported types:
    - Python primitives
    - Generic containers (with annotations)
    - Literals
    - Enum classes (with caveats)
    - Pydantic models
    - TypedDict
    - MSONable objects with type adapters

    Limitations:
    - Union types must resolve to a single primitive type
    - Container types must be homogeneous
    - Map keys cannot be Union types

    Args:
        obj: A type annotation, class, or object with type annotations

    Returns:
        A PyArrow DataType corresponding to the input type

    Note:
        Union type serialization is currently unsupported in PyArrow.
        All union types are narrowed to their first non-None member.
    """
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
        obj is not typing.Any
    ), f"Cannot infer arrow type from: {RED}{obj}{RESET}, ambiguous ({BLUE}Any{RESET}) values cannot be resolved"

    if obj in PY_PRIMITIVES_TO_ARROW:
        return PY_PRIMITIVES_TO_ARROW[obj]

    if typing.get_origin(obj) in (list, tuple, set, Iterable):
        args = obj.__args__
        if len(args) == 1:
            return pa.list_(arrowize(args[0]))

        assert all(
            [
                member == args[0]
                for member in args
                if not isinstance(member, types.EllipsisType)
            ]
        ), f"Cannot infer arrow compatible primitive from iterable type containing mixed types: {RED}{obj}{RESET}"

        # once union type roundtripping is supported in pyarrow, something like this could work:
        #     return pa.dense_union(
        #         [
        #             pa.field(f"child_{idx}", arrowize(field))
        #             for idx, field, in zip(range(len(args)), args)
        #         ]
        #     )

        return pa.list_(arrowize(args[0]))

    if typing.get_origin(obj) in (Mapping, dict):
        args = typing.get_args(obj)

        assert all(
            not (
                isinstance(arg, typing._UnionGenericAlias | UnionType)  # type: ignore[attr-defined]
                and len(list(filter(lambda x: x is not types.NoneType, arg.__args__)))
                > 1
            )
            for arg in args
        ), f"""
        Cannot construct arrow map type from: {RED}{obj}{RESET}.
        Keys and values for map types must resolve to single primitive
        data type, not Union type:
            key annotation: {BLUE}{args[0]}{RESET}
            value annotation: {BLUE}{args[1]}{RESET}
        """

        return pa.map_(arrowize(args[0]), arrowize(args[1]))

    if typing.get_origin(obj) is typing.Literal:
        args = obj.__args__
        first_type = type(args[0])

        assert all(
            isinstance(member, first_type) for member in args
        ), f"Cannot infer arrow compatible primitive from literal with mixed types: {RED}{obj}{RESET}"

        return PY_PRIMITIVES_TO_ARROW[first_type]

    if typing.get_origin(obj) is NotRequired:
        return arrowize(obj.__args__[0])

    if isinstance(obj, type) and issubclass(obj, Enum):
        # making an assumption here based on knowledge of emmet + pymatgen enum classes...
        # should have better way to handle all enums to get serialized representations
        return PY_PRIMITIVES_TO_ARROW[str]

    if isinstance(obj, typing._UnionGenericAlias | UnionType):  # type: ignore[attr-defined]
        arrow_types = [
            (arg.__name__, arrowize(arg))
            for arg in list(
                filter(
                    lambda x: x is not types.NoneType,  # noqa: E721
                    obj.__args__,
                )
            )
        ]

        assert all(
            [field == arrow_types[0][1] for (field_name, field) in arrow_types]
        ), f"""
        (De)Serialization of Union types is not supported in pyarrow currently,
        narrow the types of {RED}{obj}{RESET} to resolve to a single primitive
        """
        # once union type roundtripping is supported in pyarrow, something like this could work:
        #     return pa.dense_union(
        #         [pa.field(f"{field_name}", field) for (field_name, field) in arrow_types]
        #     )

        return arrow_types[0][1]

    if isinstance(obj, ModelMetaclass):
        return pa.struct(
            [
                pa.field(
                    field_name,
                    arrowize(
                        obj.type_overrides[field_name]
                        if hasattr(obj, "type_overrides")
                        and field_name in obj.type_overrides
                        else value.annotation
                    ),
                )
                for field_name, value in obj.model_fields.items()  # type: ignore[attr-defined]
                if not value.exclude
            ]
        )

    if any(obj is str_like for str_like in (ImportString, Path)):
        return PY_PRIMITIVES_TO_ARROW[str]

    if isinstance(obj, typing._TypedDictMeta | typing_extensions._TypedDictMeta):  # type: ignore[attr-defined]
        return pa.struct(
            [
                pa.field(field_name, arrowize(value))
                for field_name, value in obj.__annotations__.items()
            ]
        )

    if isinstance(obj, typing.ForwardRef):
        if sys.version_info >= (3, 12, 4):
            # ``type_params`` were added in 3.13 and the signature of _evaluate()
            # is not backward-compatible (it was backported to 3.12.4, so anything
            # before 3.12.4 still has the old signature).
            # See: https://github.com/python/cpython/pull/118104.
            return arrowize(
                obj._evaluate(globals(), locals(), {}, recursive_guard=frozenset())  # type: ignore[misc, arg-type]
            )
        return arrowize(obj._evaluate(globals(), locals(), frozenset()))

    if isinstance(obj, typing.TypeVar):
        return arrowize(obj.__constraints__[1])

    if isinstance(obj, typing._AnnotatedAlias):  # type: ignore[attr-defined]
        return arrowize(obj.__args__[0])

    if isinstance(obj, type) and issubclass(obj, MSONable):
        assert hasattr(
            obj, "__type_adapter__"
        ), f"""
        No serialization adapter is specified for msonable obj: {RED}{obj}{RESET}.
        TypeVars can be written for external classes in the types.pymatgen_types module.
        Internal classes may use the set_msonable_type_adapter decorator.
        """

        return arrowize(obj.__type_adapter__.model_fields["root"].annotation)

    if isinstance(obj, type):
        return arrowize(
            next(
                filter(
                    lambda primitive: issubclass(obj, primitive), PY_PRIMITIVES_TO_ARROW
                )
            )
        )
