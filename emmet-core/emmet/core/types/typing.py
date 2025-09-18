"""Define custom type annotations for emmet-core.

Note that only type annotations which are used across
the code base should be put here.

Types which only have one purpose / exist only within
one module, can and should remain in that module.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
import os
from pathlib import Path
from typing import Annotated, Union

from pydantic import PlainSerializer, Field, BeforeValidator

from emmet.core.mpid import MPID, AlphaID
from emmet.core.utils import utcnow, convert_datetime

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
