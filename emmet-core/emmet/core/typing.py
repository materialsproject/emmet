"""Define custom type annotations for emmet-core."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypeAlias

from pymatgen.electronic_structure.bandstructure import Kpoint
from typing_extensions import TypedDict

PathLike: TypeAlias = str | Path | os.DirEntry[str]
"""Type of a generic path-like object"""


class TypedBandDict(TypedDict):
    band_index: dict[str, list[int]]
    kpoint_index: list[int]
    kpoint: Kpoint
    energy: float
    projections: dict[str, list[list[float]]]


class TypedBandGapDict(TypedDict):
    direct: bool
    transition: str
    energy: float


class TypedBranchDict(TypedDict):
    start_index: int
    end_index: int
    name: str
