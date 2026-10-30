import typing
from datetime import datetime
from pathlib import Path

import pyarrow as pa
from pydantic.types import ImportString

from emmet.core.types.introspection import Kind, TypeShape, classify

RED = "\033[31m"
BLUE = "\033[34m"
RESET = "\033[0m"

PY_PRIMITIVES_TO_ARROW = {
    int: pa.int64(),
    float: pa.float64(),
    str: pa.string(),
    bool: pa.bool_(),
    datetime: pa.timestamp("us", tz="UTC"),
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
    return _arrowize(classify(obj))


def _arrowize(shape: TypeShape) -> pa.DataType:
    """Fold the shape of a type into a pyarrow data type."""
    obj = shape.tp

    assert obj not in (
        list,
        tuple,
        set,
        dict,
        typing.Dict,  # noqa: UP006
        typing.List,  # noqa: UP006
        typing.Set,  # noqa: UP006
        typing.Tuple,  # noqa: UP006
    ), f"Cannot construct arrow type from container of type {RED}{obj}{RESET} without typed arguments"

    assert (
        shape.kind is not Kind.ANY
    ), f"Cannot infer arrow type from: {RED}{obj}{RESET}, ambiguous ({BLUE}Any{RESET}) values cannot be resolved"

    match shape.kind:
        case Kind.SEQUENCE | Kind.TUPLE:
            args = shape.args
            if len(args) == 1:
                return pa.list_(_arrowize(shape.child(args[0])))

            assert all(
                member == args[0] for member in args
            ), f"Cannot infer arrow compatible primitive from iterable type containing mixed types: {RED}{obj}{RESET}"

            # once union type roundtripping is supported in pyarrow, something like this could work:
            #     return pa.dense_union(
            #         [
            #             pa.field(f"child_{idx}", arrowize(field))
            #             for idx, field, in zip(range(len(args)), args)
            #         ]
            #     )

            return pa.list_(_arrowize(shape.child(args[0])))

        case Kind.MAPPING:
            args = shape.args
            kinds = [shape.child(arg) for arg in args]

            assert all(
                not (arg.kind is Kind.UNION and len(arg.args) > 1) for arg in kinds
            ), f"""
            Cannot construct arrow map type from: {RED}{obj}{RESET}.
            Keys and values for map types must resolve to single primitive
            data type, not Union type:
                key annotation: {BLUE}{args[0]}{RESET}
                value annotation: {BLUE}{args[1]}{RESET}
            """

            return pa.map_(_arrowize(kinds[0]), _arrowize(kinds[1]))

        case Kind.LITERAL:
            first_type = type(shape.args[0])

            assert all(
                isinstance(member, first_type) for member in shape.args
            ), f"Cannot infer arrow compatible primitive from literal with mixed types: {RED}{obj}{RESET}"

            return PY_PRIMITIVES_TO_ARROW[first_type]

        case Kind.ENUM:
            # making an assumption here based on knowledge of emmet + pymatgen enum classes...
            # should have better way to handle all enums to get serialized representations
            return PY_PRIMITIVES_TO_ARROW[str]

        case Kind.UNION:
            arrow_types = [_arrowize(shape.child(arg)) for arg in shape.args]

            assert all(
                field == arrow_types[0] for field in arrow_types
            ), f"""
            (De)Serialization of Union types is not supported in pyarrow currently,
            narrow the types of {RED}{obj}{RESET} to resolve to a single primitive
            """
            # once union type roundtripping is supported in pyarrow, something like this could work:
            #     return pa.dense_union(
            #         [pa.field(f"{field_name}", field) for (field_name, field) in arrow_types]
            #     )

            return arrow_types[0]

        case Kind.MODEL:
            return pa.struct(
                [
                    pa.field(field_name, _arrowize(shape.child(annotation)))
                    for field_name, annotation in shape.fields().items()
                ]
            )

        case Kind.TYPEDDICT:
            return pa.struct(
                [
                    pa.field(field_name, _arrowize(shape.child(annotation)))
                    for field_name, annotation in shape.fields().items()
                ]
            )

        case Kind.ANNOTATED:
            return _arrowize(shape.child(shape.args[0]))

        case Kind.MSONABLE:
            assert shape.args, f"""
            No serialization adapter is specified for msonable obj: {RED}{obj}{RESET}.
            TypeVars can be written for external classes in the types.pymatgen_types module.
            Internal classes may use the set_msonable_type_adapter decorator.
            """

            return _arrowize(shape.child(shape.args[0]))

        case Kind.CLASS:
            cls = shape.origin
            if cls in PY_PRIMITIVES_TO_ARROW:
                return PY_PRIMITIVES_TO_ARROW[cls]

            if any(cls is str_like for str_like in (ImportString, Path)):
                return PY_PRIMITIVES_TO_ARROW[str]

            return PY_PRIMITIVES_TO_ARROW[
                next(
                    filter(
                        lambda primitive: issubclass(cls, primitive),
                        PY_PRIMITIVES_TO_ARROW,
                    )
                )
            ]

    raise TypeError(f"Cannot construct arrow type from: {RED}{obj}{RESET}")
