import ddtrace.auto  # noqa: F401

import time
import uvicorn

start = time.perf_counter()
import logging

from mp_logging import configure_logging
from mp_logging.asgi import LoggingMiddleware

configure_logging(app_loggers=("emmet", "app"))
logging.getLogger("uvicorn.access").handlers = []
logging.getLogger("uvicorn.access").propagate = False
from fastapi.middleware.cors import CORSMiddleware
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
if default_settings.DEBUG:
    app.add_middleware(CORSMiddleware, expose_headers=["x-consumer-id"])
# Added last, so it wraps all other middleware (sees the final status)
app.add_middleware(LoggingMiddleware)
delta = time.perf_counter() - start
logger.warning("Startup complete", extra={"startup_seconds": round(delta, 1)})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
