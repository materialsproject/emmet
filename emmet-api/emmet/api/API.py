from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.responses import RedirectResponse

from emmet.api.resource import Resource


class API:
    """
    Basic API manager to tie together various resources.
    """

    def __init__(
        self,
        resources: dict[str, list[Resource]],
        title: str = "Generic API",
        version: str = "v0.0.0",
        debug: bool = False,
        heartbeat_meta: dict | None = None,
        description: str | None = None,
        tags_meta: list[dict] | None = None,
    ):
        """
        Args:
            resources: dictionary of resource objects and http prefix they live in
            title: a string title for this API
            version: the version for this API
            debug: turns debug on in FastAPI
            heartbeat_meta: dictionary of additional metadata to include in the heartbeat response
            description: description of the API to be used in the generated docs
            tags_meta: descriptions of tags to be used in the generated docs.
        """
        self.title = title
        self.version = version
        self.debug = debug
        self.heartbeat_meta = heartbeat_meta
        self.description = description
        self.tags_meta = tags_meta

        if len(resources) == 0:
            raise RuntimeError("ERROR: There are no endpoints provided")

        self.resources = resources

    def on_startup(self):
        """
        Basic startup that runs the resource startup functions.
        """
        for resource_list in self.resources.values():
            for resource in resource_list:
                resource.on_startup()

    @property
    def app(self):
        """
        App server for the cluster manager.
        """
        app = FastAPI(
            title=self.title,
            version=self.version,
            on_startup=[self.on_startup],
            debug=self.debug,
            description=self.description,
            openapi_tags=self.tags_meta,
        )

        # Allow requests from other domains in debug mode. This allows
        # testing with local deployments of other services. For production
        # deployment, this will be taken care of by nginx.
        if self.debug:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET"],
                allow_headers=["*"],
            )

        for prefix, resource_list in self.resources.items():
            main_resource = resource_list.pop(0)
            for resource in resource_list:
                main_resource.router.include_router(resource.router)

            app.include_router(main_resource.router, prefix=f"/{prefix}")

        app.add_middleware(GZipMiddleware, minimum_size=1000)

        @app.get("/heartbeat", include_in_schema=False)
        @app.head("/heartbeat", include_in_schema=False)
        def heartbeat():
            """API Heartbeat for Load Balancing."""
            return {
                "status": "OK",
                "time": datetime.utcnow(),
                "version": self.version,
                **self.heartbeat_meta,
            }

        @app.get("/", include_in_schema=False)
        def redirect_docs():
            """Redirects the root end point to the docs."""
            return RedirectResponse(url=app.docs_url, status_code=301)

        return app

    def run(self, ip: str = "127.0.0.1", port: int = 8000, log_level: str = "info"):
        """
        Runs the Cluster Manager locally.

        Args:
            ip: Local IP to listen on
            port: Local port to listen on
            log_level: Logging level for the webserver

        Returns:
            None
        """
        uvicorn.run(self.app, host=ip, port=port, log_level=log_level, reload=False)
