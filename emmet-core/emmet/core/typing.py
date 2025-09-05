"""Define custom type annotations for emmet-core."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Union

from pydantic import PlainSerializer

PathLike = Annotated[
    Union[str | Path | os.DirEntry[str]],
    PlainSerializer(lambda x: str(x), return_type=str),
]
"""Type of a generic path-like object"""
