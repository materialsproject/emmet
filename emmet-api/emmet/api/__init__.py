"""
Core module exposes the document interfaces
These will be ingested via Drones, built by Builders, and served via the API
"""

from importlib.metadata import version

try:
    __version__ = version("emmet-api")
except Exception:  # pragma: no cover
    # package is not installed
    pass
