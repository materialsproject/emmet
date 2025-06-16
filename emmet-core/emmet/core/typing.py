"""Define custom type annotations for emmet-core."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypeAlias

PathLike: TypeAlias = str | Path | os.DirEntry[str]
"""Type of a generic path-like object"""
