import os
from maggma.stores import MongoURIStore

resources = {}

db_uri = os.environ.get("MPCONTRIBS_MONGO_HOST", None)
db_suffix = os.environ["MAPI_DB_NAME_SUFFIX"]

if db_uri:

    # allow db_uri to be set with a different protocol scheme
    # but prepend with mongodb+srv:// if not otherwise specified
    if len(db_uri.split("://", 1)) < 2:
        db_uri = "mongodb+srv://" + db_uri

    synth_store = MongoURIStore(uri=db_uri, database="mp_core", key="_id", collection_name="synth_descriptions")

    mpcomplete_store = MongoURIStore(
        uri=db_uri, database="mp_consumers", key="submission_id", collection_name="mpcomplete"
    )

    consumer_settings_store = MongoURIStore(
        uri=db_uri, database="mp_consumers", key="consumer_id", collection_name="settings"
    )

    general_store = MongoURIStore(
        uri=db_uri, database="mp_consumers", key="submission_id", collection_name="general_store"
    )
else:
    raise RuntimeError("Must specify MongoDB URI containing inputs.")


# Synthesis
from emmet.api.routes.synthesis.resources import synth_resource

resources.update({"synthesis": [synth_resource(synth_store)]})

# MPComplete
from emmet.api.routes.mpcomplete.resources import mpcomplete_resource

resources.update({"mpcomplete": [mpcomplete_resource(mpcomplete_store)]})

# Consumers
from emmet.api.routes._consumer.resources import settings_resource

resources.update({"_user_settings": [settings_resource(consumer_settings_store)]})

# General Store
from emmet.api.routes._general_store.resources import general_store_resource

resources.update({"_general_store": [general_store_resource(general_store)]})
