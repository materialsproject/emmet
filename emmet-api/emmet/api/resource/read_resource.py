from inspect import signature
from typing import Any

import orjson
from fastapi import Depends, HTTPException, Path, Request, Response
from pymongo.errors import NetworkTimeout, PyMongoError

from emmet.api.models import Meta
from emmet.api.query_operator import QueryOperator, SparseFieldsQuery
from emmet.api.resource import HintScheme, CollectionResource
from emmet.api.resource.utils import (
    attach_query_ops,
    generate_query_pipeline,
    get_count_kwargs,
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
        enable_get_by_key: bool = False,
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
            enable_get_by_key: Enable get by key route for endpoint.
            hint_scheme: The hint scheme to use for this resource
            query_to_configure_on_request: Query operator to configure on request
        """
        self.disable_validation = disable_validation
        self.enable_default_search = enable_default_search
        self.enable_get_by_key = enable_get_by_key
        self.hint_scheme = hint_scheme
        self.query_to_configure_on_request = query_to_configure_on_request

        super().__init__(*args, **kwargs)

    def prepare_endpoint(self):
        """
        Internal method to prepare the endpoint by setting up default handlers
        for routes.
        """
        if self.enable_get_by_key:
            self.build_get_by_key()

        if self.enable_default_search:
            self.build_dynamic_model_search()

    def build_get_by_key(self):
        key_name = self.collection_key
        model_name = self.model.__name__

        if self.key_fields is None:
            field_input = SparseFieldsQuery(
                self.model, [self.collection_key, "last_updated"]
            ).query
        else:

            def field_input():
                return {"properties": self.key_fields}

        async def get_by_key(
            request: Request,
            temp_response: Response,
            key: str = Path(
                ...,
                alias=key_name,
                title=f"The {key_name} of the {model_name} to get",
            ),
            _fields: STORE_PARAMS = Depends(field_input),
        ):
            f"""
            Gets a document by the primary key in the store

            Args:
                {key_name}: the id of a single {model_name}

            Returns:
                a single {model_name} document
            """

            try:
                item = [
                    await self.collection.find_one(
                        {self.collection_key: key},
                        {field: 1 for field in _fields.get("properties", [])},
                        maxTimeMS=self.timeout,
                    )
                ]
            except (NetworkTimeout, PyMongoError) as e:
                if e.timeout:
                    raise HTTPException(
                        status_code=504,
                        detail="Server timed out trying to obtain data. Try again with a smaller request.",
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                    )

            if item == [None]:
                raise HTTPException(
                    status_code=404,
                    detail=f"Item with {self.collection_key} = {key} not found",
                )

            for operator in self.query_operators:
                item = operator.post_process(item, {})

            response = {"data": item}  # type: ignore

            if self.disable_validation:
                response = Response(orjson.dumps(response, default=serialization_helper))  # type: ignore

            if self.header_processor is not None:
                if self.disable_validation:
                    self.header_processor.process_header(response, request)
                else:
                    self.header_processor.process_header(temp_response, request)

            return response

        self.router.get(
            f"{self.sub_path}{{{key_name}}}/",
            summary=f"Get a {model_name} document by by {key_name}",
            response_description=f"Get a {model_name} document by {key_name}",
            response_model=self.response_model,
            response_model_exclude_unset=True,
            tags=self.tags,
            include_in_schema=self.include_in_schema,
        )(get_by_key)

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
            query["maxTimeMS"] = self.timeout

            if self.hint_scheme is not None:  # pragma: no cover
                hints = self.hint_scheme.generate_hints(query)
                query.update(hints)

            try:
                count = await self.collection.count_documents(
                    query.get("criteria") or {},
                    **get_count_kwargs(query),
                )

                pipeline = generate_query_pipeline(query)
                cursor = await self.collection.aggregate(
                    pipeline, hint=query.get("agg_hint"), maxTimeMS=self.timeout
                )
                data = await cursor.to_list()
            except (NetworkTimeout, PyMongoError) as e:
                if e.timeout:
                    raise HTTPException(
                        status_code=504,
                        detail="Server timed out trying to obtain data. Try again with a smaller request.",
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="Server timed out trying to obtain data. Try again with a smaller request,"
                        " or remove sorting fields and sort data locally.",
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
