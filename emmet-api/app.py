from material_resources import resources as materials_resources
from mpcule_resources import resources as mpcule_resources

from emmet.api.core.api import MAPI
from emmet.api.core.documentation import description, tags_meta
from emmet.api.core.settings import MAPISettings

default_settings = MAPISettings()

resources = {**materials_resources, **mpcule_resources}

api = MAPI(resources=resources, debug=default_settings.DEBUG, description=description, tags_meta=tags_meta)
app = api.app
