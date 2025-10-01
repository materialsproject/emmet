"""Define custom type annotations for emmet-core.

Note that only type annotations which are used across
the code base should be put here.

Types which only have one purpose / exist only within
one module, can and should remain in that module.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Union

from pydantic import BeforeValidator, Field, PlainSerializer
from typing_extensions import TypedDict

from emmet.core.mpid import MPID, AlphaID
from emmet.core.types.pymatgen_types.kpoint_adapter import KpointType
from emmet.core.utils import convert_datetime, utcnow

if TYPE_CHECKING:
    from typing import Any

    from typing_extensions import TypeAlias

FSPathType: TypeAlias = Annotated[
    Union[str | Path | os.DirEntry[str] | os.PathLike[str]],
    PlainSerializer(lambda x: str(x), return_type=str),
]
"""Type of a generic path-like object"""

DateTimeType: TypeAlias = Annotated[
    datetime,
    Field(default_factory=utcnow),
    PlainSerializer(
        lambda x: x.isoformat() if isinstance(x, datetime) else x, return_type=str
    ),
    BeforeValidator(lambda x: convert_datetime(x)),
]
"""Datetime serde."""


def _fault_tolerant_id_serde(val: Any, serialize: bool = False) -> Any:
    """Needed for the API and safe de-/serialization behavior."""
    try:
        alpha_id = AlphaID(val)
        if serialize:
            return str(alpha_id)
        return alpha_id.formatted
    except Exception:
        return val


IdentifierType: TypeAlias = Annotated[
    Union[MPID, AlphaID],
    BeforeValidator(_fault_tolerant_id_serde),
    PlainSerializer(lambda x: _fault_tolerant_id_serde(x, serialize=True)),
]
"""MPID / AlphaID serde."""


class TypedBandDict(TypedDict):
    """Type def for data stored for cbms or vbms"""

    band_index: dict[str, list[int]]
    kpoint_index: list[int]
    kpoint: KpointType
    energy: float
    projections: dict[str, list[list[float]]]
