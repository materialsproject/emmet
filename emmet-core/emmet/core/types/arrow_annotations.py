"""Arrow type annotations for schema definitions, with no pyarrow dependency.

Models can use these aliases to declare how a field should be stored in
arrow (e.g., float32 or large_list columns) without importing pyarrow.
pyarrow is only imported when `emmet.core.arrow.arrowize` resolves the type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    import pyarrow as pa


@dataclass(frozen=True)
class ArrowType:
    """Annotated metadata which forces the arrow type of an annotation.

    Use with `typing.Annotated` when the arrow type cannot be inferred from
    the python type alone, e.g., a float32 or large_list column:

        Annotated[list[float], ArrowType(my_dtype_factory)]

    The arrow type is given as a zero-argument factory, and is only called
    (and pyarrow only imported) when `dtype` is accessed. This keeps schema
    modules importable without pyarrow installed.

    Pydantic ignores this metadata, so validation and serialization are
    unchanged. Only `arrowize` reads it. Note that pyarrow only applies the
    type if a table is constructed with the schema produced by `arrowize`,
    otherwise it infers types from the python values.
    """

    factory: Callable[[], pa.DataType]

    @property
    def dtype(self) -> pa.DataType:
        """Build the arrow data type. Requires pyarrow."""
        return self.factory()


def _float32_list() -> pa.DataType:
    import pyarrow as pa

    return pa.list_(pa.float32())


def _float32_grid() -> pa.DataType:
    import pyarrow as pa

    return pa.large_list(pa.float32())


def _float32_matrix() -> pa.DataType:
    import pyarrow as pa

    return pa.list_(pa.list_(pa.float32()))


Float32List = Annotated[list[float], ArrowType(_float32_list)]
"""List of floats stored as float32 in arrow."""

Float32Grid = Annotated[list[float], ArrowType(_float32_grid)]
"""Flattened list of floats stored as float32 with 64-bit offsets in arrow.

For very large arrays (volumetric data) where the total number of values
in a column chunk can exceed the 2**31 - 1 limit of 32-bit list offsets.
"""

Float32Matrix = Annotated[list[list[float]], ArrowType(_float32_matrix)]
"""Nested list of floats stored as float32 in arrow."""


def _float64_grid() -> pa.DataType:
    import pyarrow as pa

    return pa.large_list(pa.float64())


Float64Grid = Annotated[list[float], ArrowType(_float64_grid)]
"""Flattened list of floats stored as float64 with 64-bit offsets in arrow.

The doubles counterpart of `Float32Grid`, for arrays that need the precision, such as
the energies, coordinates and forces of a trajectory.
"""


def _array_validator(dtype: str):
    """A validator for a field that is a 1-D numpy array of a given type.

    None is kept. Anything else is made an array of that type, which is not a copy if it
    already is one. The arrays are C-contiguous, as Arrow takes their buffer as it is.
    """

    def validate(value):
        import numpy as np

        if value is None:
            return None
        array = np.ascontiguousarray(value, dtype=dtype)
        if array.ndim != 1:
            raise ValueError(
                f"Expected a 1-D array, flattened in C order, not one of shape {array.shape}."
            )
        return array

    return validate


def _array_serializer(value, info):
    """The array itself when it is going to Arrow, otherwise a list, as for any JSON."""
    if value is None:
        return None
    if (info.context or {}).get("format") == "arrow":
        return value
    return value.tolist() if hasattr(value, "tolist") else list(value)


def _array_annotation(dtype: str, arrow_factory):
    from pydantic import PlainSerializer, PlainValidator, WithJsonSchema

    return Annotated[
        Any,
        PlainValidator(_array_validator(dtype)),
        PlainSerializer(_array_serializer, when_used="always"),
        WithJsonSchema({"type": "array", "items": {"type": "number"}}),
        ArrowType(arrow_factory),
    ]


Float32Array = _array_annotation("float32", _float32_grid)
"""A flattened array of floats, held as a float32 numpy array and stored as float32.

The in-memory counterpart of `Float32Grid`: a value takes 4 bytes, where a list takes 32.
A dump is a list of floats, except for the dump with the context `{"format": "arrow"}`,
which is the array itself, so that Arrow can take its buffer. Arrow stores it
with 64-bit offsets, like `Float32Grid`.
"""

Float64Array = _array_annotation("float64", _float64_grid)
"""The doubles counterpart of `Float32Array`."""
