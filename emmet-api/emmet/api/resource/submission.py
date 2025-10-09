from datetime import datetime
from enum import Enum
from inspect import signature
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Path, Request
from pydantic import Field, create_model
from pymongo.errors import NetworkTimeout, PyMongoError

from emmet.api.models import Meta
from emmet.api.query_operator import QueryOperator, SubmissionQuery
from emmet.api.resource import CollectionResource
from emmet.api.resource.utils import (
    attach_query_ops,
    generate_query_pipeline,
)
from emmet.api.utils import STORE_PARAMS, merge_queries


class SubmissionResource(CollectionResource):
    """
    Implements a REST Compatible Resource as POST and/or GET and/or PATCH URL endpoints
    for submitted data.
    """

    def __init__(
        self,
        *args,
        calculate_submission_id: bool = False,
        default_state: Any = None,
        duplicate_fields_check: list[str] | None = None,
        enable_default_search: bool = True,
        get_query_operators: list[QueryOperator],
        patch_query_operators: list[QueryOperator] | None = None,
        post_query_operators: list[QueryOperator],
        state_enum: Enum | None = None,
        get_sub_path: str | None = "/",
        patch_sub_path: str | None = "/",
        post_sub_path: str | None = "/",
        **kwargs,
    ):
        """
        Args:
            calculate_submission_id: Whether to calculate and use a submission ID as primary data key.
                If False, the store key is used instead.
            default_state: Default state value in provided state Enum
            duplicate_fields_check: Fields in model used to check for duplicates for POST data
            enable_default_search: Enable default endpoint search behavior.
            get_query_operators: Operators for the query language for get data
            patch_query_operators: Operators for the query language for patch data
            post_query_operators: Operators for the query language for post data
            state_enum: State Enum defining possible data states
            get_sub_path: GET sub-URL path for the resource.
            patch_sub_path: PATCH sub-URL path for the resource.
            post_sub_path: POST sub-URL path for the resource.
        """
        if isinstance(state_enum, Enum) and default_state not in [entry.value for entry in state_enum]:  # type: ignore
            raise RuntimeError(
                "If data is stateful a state enum and valid default value must be provided"
            )

        self.calculate_submission_id = calculate_submission_id
        self.default_state = default_state
        self.duplicate_fields_check = duplicate_fields_check
        self.enable_default_search = enable_default_search
        self.get_query_operators = (
            [op for op in get_query_operators if op is not None] + [SubmissionQuery(state_enum)]  # type: ignore
            if state_enum is not None
            else get_query_operators
        )
        self.patch_query_operators = patch_query_operators
        self.post_query_operators = post_query_operators
        self.state_enum = state_enum
        self.get_sub_path = get_sub_path
        self.patch_sub_path = patch_sub_path
        self.post_sub_path = post_sub_path

        new_fields = {}  # type: dict
        if self.calculate_submission_id:
            new_fields["submission_id"] = (
                str,
                Field(..., description="Unique submission ID"),
            )

        if state_enum is not None:
            new_fields["state"] = (
                list[state_enum],  # type: ignore
                Field(..., description="List of data status descriptions"),
            )

            new_fields["updated"] = (
                list[datetime],
                Field(..., description="List of status update datetimes"),
            )

        if new_fields:
            *rest, model = args
            model = create_model(model.__name__, __base__=model, **new_fields)
            args = (*rest, model)

        super().__init__(*args, **kwargs)

    def prepare_endpoint(self):
        """
        Internal method to prepare the endpoint by setting up default handlers
        for routes.
        """
        if self.enable_default_search:
            self.build_search_data()

        self.build_get_by_key()

        self.build_post_data()

        if self.patch_query_operators:
            self.build_patch_data()

    def build_get_by_key(self):
        model_name = self.model.__name__

        key_name = (
            "submission_id" if self.calculate_submission_id else self.collection_key
        )

        async def get_by_key(
            key: str = Path(
                ...,
                alias=key_name,
                description=f"The {key_name} of the {model_name} to get",
            ),
        ):
            f"""
            Get a document using the {key_name}

            Args:
                {key_name}: the id of a single {model_name}

            Returns:
                a single {model_name} document
            """

            crit = {key_name: key}
            try:
                item = [await self.collection.find_one(crit, max_time_ms=self.timeout)]
            except (NetworkTimeout, PyMongoError) as e:
                if e.timeout:
                    raise HTTPException(
                        status_code=504,
                        detail="Server timed out trying to obtain data. Try again with a smaller request.",
                    )
                else:
                    raise HTTPException(status_code=500)

            if item == [None]:
                raise HTTPException(
                    status_code=404,
                    detail=f"Item with submission ID = {key} not found",
                )

            for operator in self.get_query_operators:  # type: ignore
                item = operator.post_process(item, {})

            return {"data": item}

        self.router.get(
            f"{self.get_sub_path}{{{key_name}}}/",
            response_description=f"Get an {model_name} by {key_name}",
            response_model=self.response_model,
            response_model_exclude_unset=True,
            tags=self.tags,
            include_in_schema=self.include_in_schema,
        )(get_by_key)

    def get_search_kwargs(self, query: dict) -> dict:
        kwargs = dict(maxTimeMS=self.timeout)
        if hint := query.get("hint"):
            kwargs["hint"] = hint
        return kwargs

    def build_search_data(self):
        model_name = self.model.__name__

        async def search(**queries: STORE_PARAMS):
            request: Request = queries.pop("request")  # type: ignore
            queries.pop("temp_response")  # type: ignore

            query: STORE_PARAMS = merge_queries(list(queries.values()))

            query_params = [
                entry
                for _, i in enumerate(self.get_query_operators)  # type: ignore
                for entry in signature(i.query).parameters
            ]

            overlap = [key for key in request.query_params if key not in query_params]
            if any(overlap):
                raise HTTPException(
                    status_code=404,
                    detail="Request contains query parameters which cannot be used: {}".format(
                        ", ".join(overlap)
                    ),
                )

            try:
                count = await self.collection.count_documents(
                    query.get("criteria") or {}, **self.get_search_kwargs(query)
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
                    raise HTTPException(status_code=500)

            meta = Meta(total_doc=count)

            for operator in self.get_query_operators:  # type: ignore
                data = operator.post_process(data, query)

            return {"data": data, "meta": meta.dict()}

        self.router.get(
            self.get_sub_path,
            tags=self.tags,
            summary=f"Get {model_name} data",
            response_model=self.response_model,
            response_description="Search for {model_name} data",
            response_model_exclude_unset=True,
            include_in_schema=self.include_in_schema,
        )(attach_query_ops(search, self.get_query_operators))

    def build_post_data(self):
        model_name = self.model.__name__

        async def post_data(**queries: STORE_PARAMS):
            request: Request = queries.pop("request")  # type: ignore
            queries.pop("temp_response")  # type: ignore

            query: STORE_PARAMS = merge_queries(list(queries.values()))

            query_params = [
                entry
                for _, i in enumerate(self.post_query_operators)  # type: ignore
                for entry in signature(i.query).parameters
            ]

            overlap = [key for key in request.query_params if key not in query_params]
            if any(overlap):
                raise HTTPException(
                    status_code=404,
                    detail="Request contains query parameters which cannot be used: {}".format(
                        ", ".join(overlap)
                    ),
                )

            # Check for duplicate entry
            if self.duplicate_fields_check:
                duplicate = await self.collection.find_one(
                    {
                        field: query["criteria"][field]
                        for field in self.duplicate_fields_check
                    }
                )

                if duplicate:
                    raise HTTPException(
                        status_code=400,
                        detail="Submission already exists. Duplicate data found for fields: {}".format(
                            ", ".join(self.duplicate_fields_check)
                        ),
                    )

            if self.calculate_submission_id:
                query["criteria"]["submission_id"] = str(uuid4())

            if self.state_enum is not None:
                query["criteria"]["state"] = [self.default_state]
                query["criteria"]["updated"] = [datetime.utcnow()]

            try:
                # TODO: verify that this is only used to insert new data and one item at a time
                await self.collection.update_one(
                    filter=query["criteria"],
                    update={"$set": query["criteria"]},
                    upsert=True,
                )
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="Problem when trying to post data.",
                )

            return {
                "data": query["criteria"],
                "meta": "Submission successful",
            }

        self.router.post(
            self.post_sub_path,
            tags=self.tags,
            summary=f"Post {model_name} data",
            response_model=None,
            response_description=f"Post {model_name} data",
            response_model_exclude_unset=True,
            include_in_schema=self.include_in_schema,
        )(attach_query_ops(post_data, self.post_query_operators))

    def build_patch_data(self):
        model_name = self.model.__name__

        async def patch_data(**queries: STORE_PARAMS):
            request: Request = queries.pop("request")  # type: ignore
            queries.pop("temp_response")  # type: ignore

            query: STORE_PARAMS = merge_queries(list(queries.values()))

            query_params = [
                entry
                for _, i in enumerate(self.patch_query_operators)  # type: ignore
                for entry in signature(i.query).parameters
            ]

            overlap = [key for key in request.query_params if key not in query_params]
            if any(overlap):
                raise HTTPException(
                    status_code=404,
                    detail="Request contains query parameters which cannot be used: {}".format(
                        ", ".join(overlap)
                    ),
                )

            # Check for duplicate entry
            if self.duplicate_fields_check:
                duplicate = await self.collection.find_one(
                    {
                        field: query["criteria"][field]
                        for field in self.duplicate_fields_check
                    }
                )

                if duplicate:
                    raise HTTPException(
                        status_code=400,
                        detail="Submission already exists. Duplicate data found for fields: {}".format(
                            ", ".join(self.duplicate_fields_check)
                        ),
                    )

            if self.calculate_submission_id:
                query["criteria"]["submission_id"] = str(uuid4())

            if self.state_enum is not None:
                query["criteria"]["state"] = [self.default_state]
                query["criteria"]["updated"] = [datetime.utcnow()]

            if query.get("update"):
                try:
                    await self.collection.update_one(
                        filter=query["criteria"],
                        update={"$set": query["update"]},
                        upsert=False,
                    )
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail="Problem when trying to patch data.",
                    )

            return {
                "data": query["update"],
                "meta": "Submission successful",
            }

        self.router.patch(
            self.patch_sub_path,
            tags=self.tags,
            summary=f"Patch {model_name} data",
            response_model=None,
            response_description=f"Patch {model_name} data",
            response_model_exclude_unset=True,
            include_in_schema=self.include_in_schema,
        )(attach_query_ops(patch_data, self.patch_query_operators))
