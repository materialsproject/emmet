import time
start = time.perf_counter()
import logging

from material_resources import resources as materials_resources
from molecule_resources import resources as molecule_resources

from emmet.api.core.api import MAPI
from emmet.api.core.documentation import description, tags_meta
from emmet.api.core.settings import MAPISettings

logger = logging.getLogger(__name__)
default_settings = MAPISettings()

resources = {**materials_resources, **molecule_resources}

api = MAPI(
    resources=resources,
    debug=default_settings.DEBUG,
    description=description,
    tags_meta=tags_meta,
)
app = api.app
delta = time.perf_counter() - start
logger.warning(f"Startup took {delta:.1f}s")
