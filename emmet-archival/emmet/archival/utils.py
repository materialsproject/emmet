"""Define utility functions."""

from __future__ import annotations

from pathlib import Path

from monty.os.path import zpath as _monty_zpath

from emmet.core.types.enums import ValueEnum


class CompressionType(ValueEnum):
    """Magic bytes for commonly-used compression methods."""

    GZIP = b"\x1f\x8b"
    ZSTD = b"\x28\xb5\x2f\xfd"
    AUTO_DETECT = "auto_detect"


def zpath(target_path: str | Path) -> Path:
    """
    Wrap monty's zpath to ensure it always returns a .Path.

    Parameters
    -----------
    target_path : str or Path

    Returns
    -----------
    Path corresponding to the input path, returning the appropriate
    zip extension if that path exists.
    """
    return Path(_monty_zpath(str(target_path)))
