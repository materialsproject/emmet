import logging

from emmet.cli.legacy.settings import EmmetCLISettings

SETTINGS = EmmetCLISettings()
logging.basicConfig(
    level=logging.INFO, format="%(name)-12s: %(levelname)-8s %(message)s"
)
