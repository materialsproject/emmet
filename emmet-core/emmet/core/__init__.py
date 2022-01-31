"""
Core module exposes the document interfaces
These will be ingested via Drones, built by Builders, and served via the API
"""
from pkg_resources import DistributionNotFound, get_distribution

try:
    __version__ = get_distribution("emmet-core").version
except DistributionNotFound:  # pragma: no cover
    # package is not installed
    pass
