from inspect import signature
from typing import Any

import orjson
from fastapi import HTTPException, Request, Response
from pymongo.errors import NetworkTimeout, PyMongoError

from emmet.api.models import Meta
from emmet.api.resource import CollectionResource
from emmet.api.resource.utils import (
    attach_query_ops,
    generate_query_pipeline,
)
from emmet.api.utils import STORE_PARAMS, merge_queries, serialization_helper


class PostOnlyResource(CollectionResource):
    """
    Implements a REST Compatible Resource as a POST URL endpoint.
    """

    def __init__(
        self,
        *args,
        query: dict | None = None,
        disable_validation: bool = False,
        **kwargs,
    ):
        """
        Args:
            query: Additional criteria to apply to every request
            disable_validation: Whether to use ORJSON and provide a direct FastAPI response.
                Note this will disable auto JSON serialization and response validation with the
                provided model.
        """
        self.query = query or {}
        self.disable_validation = disable_validation

        super().__init__(*args, **kwargs)

    def prepare_endpoint(self):
        """
        Internal method to prepare the endpoint by setting up default handlers
        for routes.
        """
        self.build_dynamic_model_search()

    def get_search_kwargs(self, query: dict) -> dict:
        kwargs = dict(maxTimeMS=self.timeout)
        if hint := query.get("hint"):
            kwargs["hint"] = hint
        return kwargs

    def build_dynamic_model_search(self):
        model_name = self.model.__name__

        async def search(**queries: dict[str, STORE_PARAMS]) -> dict | Response:
            request: Request = queries.pop("request")  # type: ignore
            queries.pop("temp_response")  # type: ignore

            query_params = [
                entry
                for _, i in enumerate(self.query_operators)
                for entry in signature(i.query).parameters
            ]

            overlap = [key for key in request.query_params if key not in query_params]
            if any(overlap):
                raise HTTPException(
                    status_code=400,
                    detail="Request contains query parameters which cannot be used: {}".format(
                        ", ".join(overlap)
                    ),
                )

            query: dict[Any, Any] = merge_queries(list(queries.values()))  # type: ignore
            query["criteria"].update(self.query)

            try:
                count = await self.collection.count_documents(
                    query["criteria"], **self.get_search_kwargs(query)
                )

                pipeline = generate_query_pipeline(query)

                cursor = await self.collection.aggregate(
                    pipeline, **self.get_search_kwargs(query)
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
                        detail="Server timed out trying to obtain data. Try again with a smaller request, "
                        "or remove sorting fields and sort data locally.",
                    )

            operator_meta = {}

            for operator in self.query_operators:
                data = operator.post_process(data, query)
                operator_meta.update(operator.meta())

            meta = Meta(total_doc=count)
            response_payload = {"data": data, "meta": {**meta.dict(), **operator_meta}}

            if self.disable_validation:
                response = Response(
                    orjson.dumps(response_payload, default=serialization_helper),
                    media_type="application/json",
                )
                if self.header_processor is not None:
                    self.header_processor.process_header(response, request)
                return response

            return response_payload

        self.router.post(
            self.sub_path,
            tags=self.tags,
            summary=f"Post {model_name} documents",
            response_model=self.response_model,
            response_description=f"Post {model_name} data",
            response_model_exclude_unset=True,
        )(attach_query_ops(search, self.query_operators))
