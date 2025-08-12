from inspect import signature
from typing import Any, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel
from pymongo import timeout as query_timeout
from pymongo.errors import NetworkTimeout, PyMongoError

from emmet.api.models import Meta, Response
from emmet.api.query_operator import PaginationQuery, QueryOperator, SparseFieldsQuery
from emmet.api.resource import Resource
from emmet.api.resource.utils import attach_query_ops, generate_query_pipeline
from emmet.api.utils import STORE_PARAMS, merge_queries
from maggma.core import Store
from maggma.stores import S3Store


class PostOnlyResource(Resource):
    """
    Implements a REST Compatible Resource as a POST URL endpoint.
    """

    def __init__(
        self,
        store: Store,
        model: type[BaseModel],
        tags: Optional[list[str]] = None,
        query_operators: Optional[list[QueryOperator]] = None,
        key_fields: Optional[list[str]] = None,
        query: Optional[dict] = None,
        timeout: Optional[int] = None,
        include_in_schema: Optional[bool] = True,
        sub_path: Optional[str] = "/",
    ):
        """
        Args:
            store: The Maggma Store to get data from
            model: The pydantic model this Resource represents
            tags: List of tags for the Endpoint
            query_operators: Operators for the query language
            key_fields: List of fields to always project. Default uses SparseFieldsQuery
                to allow user to define these on-the-fly.
            timeout: Time in seconds Pymongo should wait when querying MongoDB
                before raising a timeout error
            include_in_schema: Whether the endpoint should be shown in the documented schema.
            sub_path: sub-URL path for the resource.
        """
        self.store = store
        self.tags = tags or []
        self.query = query or {}
        self.key_fields = key_fields
        self.versioned = False
        self.timeout = timeout

        self.include_in_schema = include_in_schema
        self.sub_path = sub_path
        self.response_model = Response[model]  # type: ignore

        self.query_operators = (
            query_operators
            if query_operators is not None
            else [
                PaginationQuery(),
                SparseFieldsQuery(
                    model,
                    default_fields=[self.store.key, self.store.last_updated_field],
                ),
            ]
        )

        super().__init__(model)

    def prepare_endpoint(self):
        """
        Internal method to prepare the endpoint by setting up default handlers
        for routes.
        """
        self.build_dynamic_model_search()

    def build_dynamic_model_search(self):
        model_name = self.model.__name__

        def search(**queries: dict[str, STORE_PARAMS]) -> dict:
            request: Request = queries.pop("request")  # type: ignore
            queries.pop("temp_response")  # type: ignore

            query_params = [
                entry for _, i in enumerate(self.query_operators) for entry in signature(i.query).parameters
            ]

            overlap = [key for key in request.query_params if key not in query_params]
            if any(overlap):
                raise HTTPException(
                    status_code=400,
                    detail="Request contains query parameters which cannot be used: {}".format(", ".join(overlap)),
                )

            query: dict[Any, Any] = merge_queries(list(queries.values()))  # type: ignore
            query["criteria"].update(self.query)

            self.store.connect()

            try:
                with query_timeout(self.timeout):
                    count = self.store.count(  # type: ignore
                        **{field: query[field] for field in query if field in ["criteria", "hint"]}
                    )

                    if isinstance(self.store, S3Store):
                        data = list(self.store.query(**query))  # type: ignore
                    else:
                        pipeline = generate_query_pipeline(query, self.store)

                        data = list(
                            self.store._collection.aggregate(
                                pipeline,
                                **{field: query[field] for field in query if field in ["hint"]},
                            )
                        )
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
            return {"data": data, "meta": {**meta.dict(), **operator_meta}}

        self.router.post(
            self.sub_path,
            tags=self.tags,
            summary=f"Post {model_name} documents",
            response_model=self.response_model,
            response_description=f"Post {model_name} data",
            response_model_exclude_unset=True,
        )(attach_query_ops(search, self.query_operators))
