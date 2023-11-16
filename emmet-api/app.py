import time

start = time.perf_counter()
import logging

logging.getLogger("uvicorn.access").handlers = []
from asgi_logger import AccessLoggerMiddleware
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
app.add_middleware(
    AccessLoggerMiddleware,
    format='%(h)s %(t)s %(m)s %(U)s?%(q)s %(H)s %(s)s %(b)s "%(f)s" "%(a)s" %(D)s %(p)s %({x-consumer-id}i)s',
)
app.add_middleware(CORSMiddleware, expose_headers=["x-consumer-id"])
delta = time.perf_counter() - start
logger.warning(f"Startup took {delta:.1f}s")
