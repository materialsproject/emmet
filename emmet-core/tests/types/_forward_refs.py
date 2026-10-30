"""TypedDicts with forward references nested inside containers.

Deliberately *without* `from __future__ import annotations`: the references
below are then plain strings (or `ForwardRef`s which do not know their module)
inside of the generic types, rather than whole stringified annotations.
"""

from typing import NotRequired, Optional, TypedDict


class Inner(TypedDict):
    value: int


class InList(TypedDict):
    x: list["Inner"]


class InOptional(TypedDict):
    x: NotRequired[Optional["Inner"]]


class InDict(TypedDict):
    x: dict[str, "Inner"]
