import os

from pymongo import AsyncMongoClient

from emmet.api.core.settings import MAPISettings
from emmet.api.resource.utils import CollectionWithKey

resources = {}

default_settings = MAPISettings()  # type: ignore

db_uri = os.environ.get("MPMATERIALS_MONGO_HOST", None)
db_version = default_settings.DB_VERSION
db_suffix = os.environ["MAPI_DB_NAME_SUFFIX"]


if db_uri:
    # allow db_uri to be set with a different protocol scheme
    # but prepend with mongodb+srv:// if not otherwise specified
    if len(db_uri.split("://", 1)) < 2:
        db_uri = "mongodb+srv://" + db_uri

    mongo_client = AsyncMongoClient(db_uri)
    db = mongo_client["mp_dev"]
    task_store = CollectionWithKey(db["msdefect_defect_tasks"], "task_id")
else:
    raise RuntimeError("Must specify MongoDB URI containing inputs.")

defect_resources = list()

# Tasks
from emmet.api.routes.defects.tasks.resources import task_resource

#

defect_resources.extend(
    [
        task_resource(task_store),
    ]
)

resources = {"defects": defect_resources}
