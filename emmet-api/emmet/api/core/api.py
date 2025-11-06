from fastapi.openapi.utils import get_openapi
from emmet.api.API import API
from emmet.api.resource.core import Resource
from pymatgen.core import __version__ as pmg_version  # type: ignore

from emmet.api import __version__ as api_version
from emmet.api.core.settings import MAPISettings

SETTINGS = MAPISettings()
BATCH_IDS = (SETTINGS.ACCESS_CONTROLLED_BATCH_IDS or "").split(",")


class MAPI(API):
    """
    Core Materials API that orchestrates resources together
    """

    def __init__(
        self,
        resources: dict[str, list[Resource]],
        title="Materials Project API",
        version=api_version,
        debug=False,
        heartbeat_meta={
            "pymatgen": pmg_version,
            "db_version": SETTINGS.DB_VERSION,
            "suffix": SETTINGS.DB_NAME_SUFFIX,
            "access_controlled_batch_ids": BATCH_IDS,
        },
        description=None,
        tags_meta=None,
    ):
        super().__init__(
            resources=resources,
            title=title,
            version=version,
            debug=debug,
            heartbeat_meta=heartbeat_meta,
            description=description,
            tags_meta=tags_meta,
        )

    @property
    def app(self):
        """
        App server for the cluster manager
        """
        app = super().app

        def custom_openapi():
            openapi_schema = get_openapi(
                title=self.title,
                version=self.version,
                routes=app.routes,
                description=self.description,
                tags=self.tags_meta,
            )

            openapi_schema["components"]["securitySchemes"] = {
                "ApiKeyAuth": {
                    "descriptions": "MP API key to authorize requests",
                    "name": "X-API-KEY",
                    "in": "header",
                    "type": "apiKey",
                }
            }

            openapi_schema["security"] = [{"ApiKeyAuth": []}]

            openapi_schema["info"]["x-logo"] = {
                "url": "https://raw.githubusercontent.com/materialsproject/emmet/master/emmet-api/emmet/api/core/assets/mp_logo_small.png"  # noqa: E501
            }

            app.openapi_schema = openapi_schema
            return app.openapi_schema

        app.openapi = custom_openapi

        return app
