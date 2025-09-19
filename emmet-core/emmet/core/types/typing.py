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
    from typing_extensions import TypeAlias

FSPathType: TypeAlias = Annotated[
    Union[str | Path | os.DirEntry[str] | os.PathLike[str]],
    PlainSerializer(lambda x: str(x), return_type=str),
]
"""Type of a generic path-like object"""

DateTimeType: TypeAlias = Annotated[
    datetime,
    Field(default_factory=utcnow),
    BeforeValidator(lambda x: convert_datetime(x)),
]
"""Datetime serde."""


def _validate_index(x):
    try:
        return AlphaID(x).formatted
    except ValueError:
        return str(x)


IdentifierType: TypeAlias = Annotated[
    Union[MPID, AlphaID, str],
    BeforeValidator(_validate_index),
    PlainSerializer(lambda x: str(AlphaID(x))),
]
"""MPID / AlphaID serde."""


class TypedBandDict(TypedDict):
    """Type def for data stored for cbms or vbms"""

    band_index: dict[str, list[int]]
    kpoint_index: list[int]
    kpoint: KpointType
    energy: float
    projections: dict[str, list[list[float]]]
