"""
Core module exposes the document interfaces
These will be ingested via Drones, built by Builders, and served via the API
"""
from pkg_resources import DistributionNotFound, get_distribution

import emmet.core.stubs
from emmet.core.settings import EmmetSettings

SETTINGS = EmmetSettings()

try:
    __version__ = get_distribution("emmet-core").version
except DistributionNotFound:
    # package is not installed
    pass
