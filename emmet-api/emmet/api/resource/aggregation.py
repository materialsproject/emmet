from typing import Any

import orjson
from fastapi import HTTPException, Request, Response
from pymongo.errors import NetworkTimeout, PyMongoError

from emmet.api.models import Meta
from emmet.api.query_operator import QueryOperator
from emmet.api.resource import CollectionResource
from emmet.api.resource.utils import attach_query_ops
from emmet.api.utils import STORE_PARAMS, merge_queries, serialization_helper


class AggregationResource(CollectionResource):
    """
    Implements a REST Compatible Resource as a GET URL endpoint.
    """

    def __init__(
        self,
        *args,
        pipeline_query_operator: QueryOperator,
        **kwargs,
    ):
        """
        Args:
            pipeline_query_operator: Operator for the aggregation pipeline
        """
        self.pipeline_query_operator = pipeline_query_operator

        super().__init__(*args, **kwargs)

    def prepare_endpoint(self):
        """
        Internal method to prepare the endpoint by setting up default handlers
        for routes.
        """
        self.build_dynamic_model_search()

    def build_dynamic_model_search(self):
        model_name = self.model.__name__

        async def search(**queries: dict[str, STORE_PARAMS]) -> dict:
            request: Request = queries.pop("request")  # type: ignore
            queries.pop("temp_response")  # type: ignore

            query: dict[Any, Any] = merge_queries(list(queries.values()))  # type: ignore

            try:
                cursor = await self.collection.aggregate(
                    query["pipeline"], maxTimeMS=self.timeout
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
                    )

            count = len(data)
            data = self.pipeline_query_operator.post_process(data, query)
            operator_meta = self.pipeline_query_operator.meta()

            meta = Meta(total_doc=count)
            response = {"data": data, "meta": {**meta.dict(), **operator_meta}}
            response = Response(orjson.dumps(response, default=serialization_helper))  # type: ignore

            if self.header_processor is not None:
                self.header_processor.process_header(response, request)

            return response

        self.router.get(
            self.sub_path,
            tags=self.tags,
            summary=f"Get {model_name} documents",
            response_model=self.response_model,
            response_description=f"Get {model_name} data",
            response_model_exclude_unset=True,
        )(attach_query_ops(search, [self.pipeline_query_operator]))
