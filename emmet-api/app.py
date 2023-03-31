from material_resources import summary_store
from material_resources import resources as materials_resources
from mpcule_resources import resources as mpcule_resources
from generic_resources import resources as generic_resources

from emmet.api.core.api import MAPI
from emmet.api.core.documentation import description, tags_meta
from emmet.api.core.settings import MAPISettings

from pymatgen.core import __version__ as pmg_version  # type: ignore


summary_store.connect()
summary_meta = summary_store.query_one({}, ["builder_meta"]).get("builder_meta", {})
summary_db_version = summary_meta.get("database_version", None)
summary_store.close()

default_settings = MAPISettings(DB_VERSION=summary_db_version) if summary_db_version is not None else MAPISettings()

heartbeat_meta = {
    "pymatgen": pmg_version,
    "db_version": default_settings.DB_VERSION,
    "suffix": default_settings.DB_NAME_SUFFIX,
}

resources = {**materials_resources, **mpcule_resources, **generic_resources}

api = MAPI(
    resources=resources,
    debug=default_settings.DEBUG,
    description=description,
    tags_meta=tags_meta,
    heartbeat_meta=heartbeat_meta,
)
app = api.app
