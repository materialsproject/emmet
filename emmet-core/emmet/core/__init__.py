"""
Core module exposes the document interfaces
These will be ingested via Drones, built by Builders, and served via the API.
"""

from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec

ARROW_COMPATIBLE = find_spec("pyarrow")

try:
    __version__ = version("emmet-core")
except PackageNotFoundError:  # pragma: no cover
    # package is not installed
    pass
