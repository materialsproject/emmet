from maggma.api.resource import ReadOnlyResource

from emmet.api.routes.materials.tasks.query_operators import (
    DeprecationQuery,
    MultipleTaskIDsQuery,
    TrajectoryQuery,
    EntryQuery,
    LastUpdatedQuery,
    TaskFormulaQuery,
    TaskChemsysQuery,
    TaskElementsQuery,
    TaskTypeQuery,
    CalcTypeQuery,
    RunTypeQuery,
    BatchQuery,
    FacetQuery,
)
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.core.tasks import DeprecationDoc, TaskDoc, TrajectoryDoc, EntryDoc


from inspect import signature
from typing import Any, Optional, Union

import orjson
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel
from pymongo import timeout as query_timeout
from pymongo.errors import NetworkTimeout, PyMongoError

from maggma.api.models import Meta
from maggma.api.query_operator import (
    PaginationQuery,
    QueryOperator,
    SparseFieldsQuery,
    SortQuery,
)
from maggma.api.resource import HeaderProcessor
from maggma.api.resource.utils import attach_query_ops, generate_atlas_search_pipeline
from maggma.api.utils import STORE_PARAMS, merge_atlas_querires, serialization_helper
from maggma.core import Store
from maggma.stores import S3Store

settings = MAPISettings()  # type: ignore
timeout = MAPISettings().TIMEOUT
sort_fields = ["nelements", "chemsys", "formula_pretty", "task_id"]


class TaskReadOnlyResource(ReadOnlyResource):
    """
    Subclass for using Atlas Search for the task collection
    We need to override the build_dynamic_model_search method to use Atlas Search,
    In the future, we can make this more generic if we have Atlas search index
    for all other resources
    """

    def __init__(
        self,
        store: Store,
        model: type[BaseModel],
        tags: Optional[list[str]] = None,
        query_operators: Optional[list[QueryOperator]] = None,
        key_fields: Optional[list[str]] = None,
        header_processor: Optional[HeaderProcessor] = None,
        query_to_configure_on_request: Optional[QueryOperator] = None,
        timeout: Optional[int] = None,
        enable_get_by_key: bool = False,
        enable_default_search: bool = True,
        disable_validation: bool = False,
        query_disk_use: bool = False,
        include_in_schema: Optional[bool] = True,
        sub_path: Optional[str] = "/",
    ):
        super().__init__(
            store=store,
            model=model,
            tags=tags,
            query_operators=query_operators,
            key_fields=key_fields,
            header_processor=header_processor,
            query_to_configure_on_request=query_to_configure_on_request,
            timeout=timeout,
            enable_get_by_key=enable_get_by_key,
            enable_default_search=enable_default_search,
            disable_validation=disable_validation,
            query_disk_use=query_disk_use,
            include_in_schema=include_in_schema,
            sub_path=sub_path,
        )

    def build_dynamic_model_search(self):
        model_name = self.model.__name__

        def search(**queries: dict[str, STORE_PARAMS]) -> Union[dict, Response]:
            request: Request = queries.pop("request")  # type: ignore
            temp_response: Response = queries.pop("temp_response")  # type: ignore

            if self.query_to_configure_on_request is not None:
                # give the key name "request", arbitrary choice, as only the value gets merged into the query
                queries["groups"] = self.header_processor.configure_query_on_request(
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
            query: dict[Any, Any] = merge_atlas_querires(list(queries.values()))

            self.store.connect()

            try:
                with query_timeout(self.timeout):
                    if isinstance(self.store, S3Store):
                        self.store.count(criteria=query.get("criteria"))  # type: ignore

                        if self.query_disk_use:
                            data = list(self.store.query(**query, allow_disk_use=True))  # type: ignore
                        else:
                            data = list(self.store.query(**query))
                    else:
                        pipeline = generate_atlas_search_pipeline(query)
                        print("pipeline", pipeline)
                        data = list(self.store._collection.aggregate(pipeline))

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

            if data and "meta" in data[0] and data[0]["meta"]:
                meta = Meta(
                    total_doc=data[0]["meta"][0].get("count", {}).get("lowerBound", 1),
                    facet=data[0]["meta"][0].get("facet", {}),
                )
            else:
                meta = Meta(total_doc=0)

            response = {"data": data[0]["docs"] if data else [], "meta": {**meta.dict(), **operator_meta}}  # type: ignore

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


def task_resource(task_store):
    resource = TaskReadOnlyResource(
        task_store,
        TaskDoc,
        query_operators=[
            TaskChemsysQuery(),
            TaskElementsQuery(),
            MultipleTaskIDsQuery(),
            LastUpdatedQuery(),
            TaskFormulaQuery(),
            TaskTypeQuery(),
            CalcTypeQuery(),
            RunTypeQuery(),
            BatchQuery(),
            FacetQuery(),
            SortQuery(fields=sort_fields, max_num=1),
            PaginationQuery(),
            SparseFieldsQuery(
                TaskDoc,
                default_fields=["task_id", "formula_pretty", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Tasks"],
        sub_path="/tasks/",
        timeout=timeout,
        disable_validation=True,
    )
    return resource


def task_deprecation_resource(materials_store):
    resource = ReadOnlyResource(
        materials_store,
        DeprecationDoc,
        query_operators=[DeprecationQuery(), PaginationQuery()],
        tags=["Materials Tasks"],
        enable_default_search=True,
        sub_path="/tasks/deprecation/",
        header_processor=GlobalHeaderProcessor(),
        timeout=timeout,
    )

    return resource


def trajectory_resource(task_store):
    resource = ReadOnlyResource(
        task_store,
        TrajectoryDoc,
        query_operators=[TrajectoryQuery(), PaginationQuery()],
        key_fields=["task_id", "calcs_reversed"],
        tags=["Materials Tasks"],
        sub_path="/tasks/trajectory/",
        header_processor=GlobalHeaderProcessor(),
        timeout=timeout,
        disable_validation=True,
    )

    return resource


def entries_resource(task_store):
    resource = ReadOnlyResource(
        task_store,
        EntryDoc,
        query_operators=[EntryQuery(), PaginationQuery()],
        key_fields=[
            "task_id",
            "input",
            "output",
            "run_type",
            "task_type",
            "completed_at",
            "last_updated",
        ],
        tags=["Materials Tasks"],
        sub_path="/tasks/entries/",
        header_processor=GlobalHeaderProcessor(),
        timeout=timeout,
        disable_validation=True,
    )
    return resource
