"""
Core module exposes the document interfaces
These will be ingested via Drones, built by Builders, and served via the API
"""
from emmet.core.settings import EmmetSettings
from emmet.core._version import __version__

SETTINGS = EmmetSettings()
