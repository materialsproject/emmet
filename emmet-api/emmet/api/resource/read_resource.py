from inspect import signature
from typing import Any

import orjson
from fastapi import HTTPException, Request, Response
from pymongo.errors import NetworkTimeout, PyMongoError

from emmet.api.models import Meta
from emmet.api.query_operator import QueryOperator
from emmet.api.resource import HintScheme, CollectionResource
from emmet.api.resource.utils import (
    attach_query_ops,
    generate_query_pipeline,
)
from emmet.api.utils import STORE_PARAMS, merge_queries, serialization_helper


class ReadOnlyResource(CollectionResource):
    """
    Implements a REST Compatible Resource as a GET URL endpoint
    This class provides a number of convenience features
    including full pagination, field projection.
    """

    def __init__(
        self,
        *args,
        disable_validation: bool = False,
        enable_default_search: bool = True,
        hint_scheme: HintScheme | None = None,
        query_to_configure_on_request: QueryOperator | None = None,
        **kwargs,
    ):
        """
        Args:
            disable_validation: Whether to use ORJSON and provide a direct FastAPI response.
                Note this will disable auto JSON serialization and response validation with the
                provided model.
            enable_default_search: Enable default endpoint search behavior.
            hint_scheme: The hint scheme to use for this resource
            query_to_configure_on_request: Query operator to configure on request
        """
        self.disable_validation = disable_validation
        self.enable_default_search = enable_default_search
        self.hint_scheme = hint_scheme
        self.query_to_configure_on_request = query_to_configure_on_request

        super().__init__(*args, **kwargs)

    def prepare_endpoint(self):
        """
        Internal method to prepare the endpoint by setting up default handlers
        for routes.
        """
        if self.enable_default_search:
            self.build_dynamic_model_search()

    def get_search_kwargs(self, query: dict, typ: str) -> dict:
        kwargs = dict(maxTimeMS=self.timeout)
        if hint := query.get(f"{typ}_hint"):
            kwargs["hint"] = hint
        return kwargs

    def build_dynamic_model_search(self):
        model_name = self.model.__name__

        async def search(**queries: dict[str, STORE_PARAMS]) -> dict | Response:

            request: Request = queries.pop("request")  # type: ignore
            temp_response: Response = queries.pop("temp_response")  # type: ignore

            if self.query_to_configure_on_request is not None:
                # give the key name "request", arbitrary choice, as only the value gets merged into the query
                queries["groups"] = self.header_processor.configure_query_on_request(  # type: ignore
                    request=request, query_operator=self.query_to_configure_on_request
                )
            # allowed query parameters
            query_params = [
                entry
                for _, i in enumerate(self.query_operators)
                for entry in signature(i.query).parameters
            ]
            # check for overlap between allowed query parameters and request query parameters
            overlap = [key for key in request.query_params if key not in query_params]
            if any(overlap):
                if "limit" in overlap or "skip" in overlap:
                    raise HTTPException(
                        status_code=400,
                        detail="'limit' and 'skip' parameters have been renamed. "
                        "Please update your API client to the newest version.",
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Request contains query parameters which cannot be used: {}".format(
                            ", ".join(overlap)
                        ),
                    )
            query: dict[Any, Any] = merge_queries(list(queries.values()))  # type: ignore

            if self.hint_scheme is not None:  # pragma: no cover
                hints = self.hint_scheme.generate_hints(query)
                query.update(hints)

            try:
                crit = query.get("criteria")
                if crit:
                    count = await self.collection.count_documents(
                        crit,
                        **self.get_search_kwargs(query, "count"),
                    )
                else:
                    count = await self.collection.estimated_document_count()

                pipeline = generate_query_pipeline(query)
                cursor = await self.collection.aggregate(
                    pipeline,
                    **self.get_search_kwargs(query, "agg"),
                )
                data = await cursor.to_list()
            except (NetworkTimeout, PyMongoError) as e:
                raise HTTPException(
                    status_code=504 if e.timeout else 500,
                    detail=f"Server error: {e}",
                )

            operator_meta = {}

            for operator in self.query_operators:
                data = operator.post_process(data, query)
                operator_meta.update(operator.meta())

            meta = Meta(total_doc=count)

            response = {"data": data, "meta": {**meta.dict(), **operator_meta}}  # type: ignore

            if self.disable_validation:
                response = Response(orjson.dumps(response, default=serialization_helper))  # type: ignore

            if self.header_processor is not None:
                if self.disable_validation:
                    self.header_processor.process_header(response, request)
                else:
                    self.header_processor.process_header(temp_response, request)

            return response

        self.router.get(
            self.sub_path,
            tags=self.tags,
            summary=f"Get {model_name} documents",
            response_model=self.response_model,
            response_description=f"Search for a {model_name}",
            response_model_exclude_unset=True,
        )(attach_query_ops(search, self.query_operators))
