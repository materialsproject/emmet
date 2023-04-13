import os

from maggma.stores import MongoURIStore

from emmet.api.core.settings import MAPISettings
from emmet.api.routes.legacy.jcesr.resources import jcesr_resource

resources = {}

default_settings = MAPISettings()

db_uri = os.environ.get("MPCONTRIBS_MONGO_HOST", None)
db_version = default_settings.DB_VERSION
db_suffix = os.environ["MAPI_DB_NAME_SUFFIX"]

if db_uri:

    # allow db_uri to be set with a different protocol scheme
    # but prepend with mongodb+srv:// if not otherwise specified
    if len(db_uri.split("://", 1)) < 2:
        db_uri = "mongodb+srv://" + db_uri

    molecules_store = MongoURIStore(uri=db_uri, database="mp_core", key="task_id", collection_name="molecules")

legacy_resources = list()

legacy_resources.extend([jcesr_resource(molecules_store)])

resources.update({"legacy": legacy_resources})
