from emmet.builders.settings import EmmetBuildSettings
from pkg_resources import get_distribution, DistributionNotFound

SETTINGS = EmmetBuildSettings()

try:
    __version__ = get_distribution("emmet-builders").version
except DistributionNotFound:
    # package is not installed
    pass
