import logging
from abc import ABCMeta, abstractmethod

from fastapi import APIRouter, FastAPI, Request, Response
from monty.json import MontyDecoder, MSONable
from pydantic import BaseModel
from starlette.responses import RedirectResponse

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS, api_sanitize
from maggma.utils import dynamic_import


class Resource(MSONable, metaclass=ABCMeta):
    """
    Base class for a REST Compatible Resource.
    """

    def __init__(
        self,
        model: type[BaseModel],
    ):
        """
        Args:
            model: the pydantic model this Resource represents.
        """
        if not issubclass(model, BaseModel):
            raise ValueError("The resource model has to be a PyDantic Model")

        self.model = api_sanitize(model, allow_dict_msonable=True)
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

    def as_dict(self) -> dict:
        """
        Special as_dict implemented to convert pydantic models into strings.
        """
        d = super().as_dict()  # Ensures sub-classes serialize correctly
        d["model"] = f"{self.model.__module__}.{self.model.__name__}"
        return d

    @classmethod
    def from_dict(cls, d: dict):
        if isinstance(d["model"], str):
            d["model"] = dynamic_import(d["model"])
        d = {k: MontyDecoder().process_decoded(v) for k, v in d.items()}
        return cls(**d)


class HintScheme(MSONable, metaclass=ABCMeta):
    """
    Base class for generic hint schemes generation.
    """

    @abstractmethod
    def generate_hints(self, query: STORE_PARAMS) -> STORE_PARAMS:
        """
        This method takes in a MongoDB query and returns hints.
        """


class HeaderProcessor(MSONable, metaclass=ABCMeta):
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
