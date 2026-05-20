import os

from pymongo import AsyncMongoClient

from emmet.api.core.settings import MAPISettings
from emmet.api.resource.utils import CollectionWithKey
from emmet.api.routes.legacy.jcesr.resources import jcesr_resource
from emmet.api.routes.molecules.summary.resources import summary_resource

default_settings = MAPISettings()
db_uri = os.environ.get("MPMOLECULES_MONGO_HOST", None)

if db_uri:
    # allow db_uri to be set with a different protocol scheme
    # but prepend with mongodb+srv:// if not otherwise specified
    if len(db_uri.split("://", 1)) < 2:
        db_uri = "mongodb+srv://" + db_uri
    mongo_client = AsyncMongoClient(db_uri)
    db = mongo_client["mp_molecules"]
    vibrations_store = CollectionWithKey(db["molecules_vibrations"], "property_id")
    summary_store = CollectionWithKey(db["molecules_summary"], "molecule_id")
    jcesr_store = CollectionWithKey(db["jcesr"], "task_id")
else:
    raise RuntimeError("Must specify MongoDB URI containing inputs.")

resources = {
    "molecules": [summary_resource(summary_store), jcesr_resource(jcesr_store)]
}
