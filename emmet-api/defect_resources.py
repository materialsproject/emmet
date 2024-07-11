import os

from maggma.stores import MongoURIStore, S3Store

from emmet.api.core.settings import MAPISettings

resources = {}

default_settings = MAPISettings()  # type: ignore

db_uri = os.environ.get("MPCONTRIBS_MONGO_HOST", None)
db_version = default_settings.DB_VERSION
db_suffix = os.environ["MAPI_DB_NAME_SUFFIX"]


if db_uri:
    # allow db_uri to be set with a different protocol scheme
    # but prepend with mongodb+srv:// if not otherwise specified
    if len(db_uri.split("://", 1)) < 2:
        db_uri = "mongodb+srv://" + db_uri

    task_store = MongoURIStore(
        uri=db_uri,
        database="mp_dev",
        key="task_id",
        collection_name="msdefect_defect_tasks",
    )
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
