"""Arrow type annotations for schema definitions, with no pyarrow dependency.

Models can use these aliases to declare how a field should be stored in
arrow (e.g., float32 or large_list columns) without importing pyarrow.
pyarrow is only imported when `emmet.core.arrow.arrowize` resolves the type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

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
