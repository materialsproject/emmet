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
from typing import TYPE_CHECKING, Annotated, Union, Any

import orjson
from pydantic import BeforeValidator, Field, PlainSerializer, WrapSerializer
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
    BeforeValidator(convert_datetime),
]
"""Datetime serde."""

NullableDateTimeType: TypeAlias = Annotated[
    datetime | None,
    Field(default_factory=utcnow),
    BeforeValidator(convert_datetime),
]
"""Nullable datetime serde.

See: https://docs.pydantic.dev/latest/concepts/fields/#the-annotated-pattern
for why this separate class is necesary instead of `DateTimeType | None`
"""


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


def _ser_json_like(d, default_serializer, info):
    """Serialize a generic JSON-like object to a str for arrow, and a dict otherwise."""
    default_serialized_object = default_serializer(d, info)

    format = info.context.get("format") if info.context else None
    if format == "arrow" and default_serialized_object is not None:
        return orjson.dumps(default_serialized_object).decode()

    return default_serialized_object


def _deser_json_like(d):
    """Deserialize a generic JSON-like object from a str or object."""
    if hasattr(d, "as_dict"):
        d = d.as_dict()
    return orjson.loads(d) if isinstance(d, str | bytes) else d


JsonDictType = Annotated[
    dict[str, Any] | None,
    BeforeValidator(_deser_json_like),
    WrapSerializer(_ser_json_like),
]
"""Annotation for free-form JSON-like dict (INCAR-like, ddec6, etc.)"""

JsonListType = Annotated[
    list[Any] | None,
    BeforeValidator(_deser_json_like),
    WrapSerializer(_ser_json_like),
]
"""Annotation for free-form JSON-like list (some custodian metadata)"""


def _dict_items_zipper(
    dict_like: dict[str, Any] | list[tuple[str, Any]] | None,
) -> dict[str, Any] | None:
    """Zip output of dict(...).items() back into a dict."""
    if isinstance(dict_like, list):
        return {k: v for k, v in dict_like}
    return dict_like
