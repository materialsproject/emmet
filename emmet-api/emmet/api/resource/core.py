import logging
from abc import ABC, abstractmethod

from fastapi import APIRouter, FastAPI, Request, Response
from pydantic import BaseModel
from starlette.responses import RedirectResponse

from emmet.api.models import Response as ResponseModel
from emmet.api.query_operator import QueryOperator
from emmet.api.resource.utils import CollectionWithKey
from emmet.api.utils import STORE_PARAMS


class HintScheme(ABC):
    """
    Base class for generic hint schemes generation.
    """

    @abstractmethod
    def generate_hints(self, query: STORE_PARAMS) -> STORE_PARAMS:
        """
        This method takes in a MongoDB query and returns hints.
        """


class HeaderProcessor(ABC):
    """
    Base class for generic header processing.
    """

    @abstractmethod
    def process_header(self, response: Response, request: Request):
        """
        This method takes in a FastAPI Response object and processes a new header for it in-place.
        It can use data in the upstream request to generate the header.
        (https://fastapi.tiangolo.com/advanced/response-headers/#use-a-response-parameter).
        """

    @abstractmethod
    def configure_query_on_request(
        self, request: Request, query_operator: QueryOperator
    ) -> STORE_PARAMS:
        """
        This method takes in a FastAPI Request object and returns a query to be used in the store.
        """


class Resource(ABC):
    """
    Base class for a REST Compatible Resource.
    """

    def __init__(
        self,
        model: type[BaseModel],
        query_operators: list[QueryOperator] | None = None,
    ):
        """
        Args:
            model: the pydantic model this Resource represents.
            query_operators: Operators for the query language
        """
        if not issubclass(model, BaseModel):
            raise ValueError("The resource model has to be a PyDantic Model")

        if not hasattr(self, "response_model"):
            self.response_model = ResponseModel[model]  # type: ignore

        if not hasattr(self, "query_operators"):
            self.query_operators = (
                query_operators if query_operators is not None else []
            )

        self.model = model
        self.logger = logging.getLogger(type(self).__name__)
        self.logger.addHandler(logging.NullHandler())
        self.router = APIRouter()
        self.prepare_endpoint()
        self.setup_redirect()

    def on_startup(self):
        """
        Callback to perform some work on resource initialization.
        """

    @abstractmethod
    def prepare_endpoint(self):
        """
        Internal method to prepare the endpoint by setting up default handlers
        for routes.
        """

    def setup_redirect(self):
        @self.router.get("$", include_in_schema=False)
        def redirect_unslashed():
            """
            Redirects unforward slashed url to resource
            url with the forward slash.
            """
            url = self.router.url_path_for("/")
            return RedirectResponse(url=url, status_code=301)

    def run(self):  # pragma: no cover
        """
        Runs the Endpoint cluster locally
        This is intended for testing not production.
        """
        import uvicorn

        app = FastAPI()
        app.include_router(self.router, prefix="")
        uvicorn.run(app)


class CollectionResource(Resource):
    """
    Base class for a REST Compatible Resource that operates on a MongoDB collection.
    """

    def __init__(
        self,
        store: CollectionWithKey,
        *args,
        header_processor: HeaderProcessor | None = None,
        include_in_schema: bool = True,
        key_fields: list[str] | None = None,
        sub_path: str | None = "/",
        tags: list[str] | None = None,
        timeout: int | None = None,
        **kwargs,
    ):
        """
        Args:
            store: The store to get data from
            header_processor: The header processor to use for this resource
            include_in_schema: Whether the endpoint should be shown in the documented schema.
            key_fields: List of fields to always project. Default uses SparseFieldsQuery
                to allow user to define these on-the-fly.
            sub_path: sub-URL path for the resource.
            tags: List of tags for the Endpoint
            timeout: Time in seconds Pymongo should wait when querying MongoDB
                before raising a timeout error

        """
        self.collection = store.collection
        self.collection_key = store.key

        self.header_processor = header_processor
        self.include_in_schema = include_in_schema
        self.key_fields = key_fields
        self.sub_path = sub_path
        self.tags = tags or []
        self.timeout = (
            timeout * 1000 if timeout is not None else None
        )  # Convert to milliseconds for MongoDB

        super().__init__(*args, **kwargs)
