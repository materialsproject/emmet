from datetime import datetime, timedelta
from typing import Optional

import orjson
from botocore.exceptions import ClientError
from fastapi import HTTPException, Path, Request, Response

from emmet.api.models import Response as ResponseModel
from emmet.api.models import S3URLDoc
from emmet.api.resource import HeaderProcessor, Resource
from emmet.api.utils import serialization_helper
from maggma.stores.aws import S3Store


class S3URLResource(Resource):
    """
    Implements a REST Compatible Resource as a GET URL endpoint
    that provides pre-signed S3 URLs.
    """

    def __init__(
        self,
        store: S3Store,
        url_lifetime: int,
        tags: Optional[list[str]] = None,
        header_processor: Optional[HeaderProcessor] = None,
        disable_validation: bool = False,
        include_in_schema: Optional[bool] = True,
        sub_path: Optional[str] = "/",
    ):
        """
        Args:
            store: The Maggma Store to get data from
            url_lifetime: URL lifetime in seconds
            header_processor: The header processor to use for this resource
            disable_validation: Whether to use ORJSON and provide a direct FastAPI response.
                Note this will disable auto JSON serialization and response validation with the
                provided model.
            include_in_schema: Whether the endpoint should be shown in the documented schema.
            sub_path: sub-URL path for the resource.
        """
        self.store = store
        self.url_lifetime = url_lifetime
        self.tags = tags or []
        self.header_processor = header_processor
        self.disable_validation = disable_validation
        self.include_in_schema = include_in_schema
        self.sub_path = sub_path

        self.response_model = ResponseModel[S3URLDoc]  # type: ignore

        super().__init__(S3URLDoc)

    def prepare_endpoint(self):
        """
        Internal method to prepare the endpoint by setting up default handlers
        for routes.
        """
        self.build_get_by_key()

    def build_get_by_key(self):
        key_name = self.store.key
        model_name = self.model.__name__

        def get_by_key(
            request: Request,
            temp_response: Response,
            key: str = Path(
                ...,
                alias=key_name,
                title=f"The {key_name} of the {model_name} to get",
            ),
        ):
            f"""
            Gets a document by the primary key in the store

            Args:
                {key_name}: the id of a single {model_name}

            Returns:
                A single pre-signed URL {model_name} document
            """
            self.store.connect()

            if self.store.sub_dir is not None:
                key = self.store.sub_dir.strip("/") + "/" + key

            # Make sure object is in bucket
            try:
                self.store.s3.Object(self.store.bucket, key).load()
            except ClientError:
                raise HTTPException(
                    status_code=404,
                    detail="No object found for {} = {}".format(
                        self.store.key, key.split("/")[-1]
                    ),
                )

            # Get URL
            try:
                url = self.store.s3.meta.client.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": self.store.bucket, "Key": key},
                    ExpiresIn=self.url_lifetime,
                )
            except Exception:
                raise HTTPException(
                    status_code=404,
                    detail="Problem obtaining URL for {} = {}".format(
                        self.store.key, key.split("/")[-1]
                    ),
                )

            requested_datetime = datetime.utcnow()
            expiry_datetime = requested_datetime + timedelta(seconds=self.url_lifetime)

            item = S3URLDoc(
                url=url,
                requested_datetime=requested_datetime,
                expiry_datetime=expiry_datetime,
            )

            response = {"data": [item.dict()]}  # type: ignore

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
