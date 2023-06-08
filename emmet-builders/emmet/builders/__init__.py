from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("emmet-builders")
except PackageNotFoundError:  # pragma: no cover
    # package is not installed
    pass
