import logging
from importlib.metadata import PackageNotFoundError, version

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

try:
    __version__ = version("emmet-archival")
except PackageNotFoundError:  # pragma: no cover
    # package is not installed
    pass
