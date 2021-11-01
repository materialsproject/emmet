from pkg_resources import DistributionNotFound, get_distribution

from emmet.builders.settings import EmmetBuildSettings

SETTINGS = EmmetBuildSettings()

try:
    __version__ = get_distribution("emmet-builders").version
except DistributionNotFound:  # pragma: no cover
    # package is not installed
    pass
