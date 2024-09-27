from maggma.api.resource.core import HeaderProcessor
from fastapi import Response, Request
from maggma.api.utils import STORE_PARAMS
from emmet.api.routes.materials.materials.query_operators import LicenseQuery


class GlobalHeaderProcessor(HeaderProcessor):
    def process_header(self, response: Response, request: Request):
        groups = request.headers.get("X-Authenticated-Groups", None)
        if groups is not None and "api_all_nolimit" in [
            group.strip() for group in groups.split(",")
        ]:
            response.headers["X-Bypass-Rate-Limit"] = "ALL"

        # forward Consumer Id header in response
        consumer_id = request.headers.get("X-Consumer-Id", "-")
        response.headers["X-Consumer-Id"] = consumer_id

    def configure_query_on_request(
        self, request: Request, query_operator: LicenseQuery
    ) -> STORE_PARAMS:
        groups = request.headers.get("x-consumer-groups", None)
        privileged_groups = {"TERMS:ACCEPT-NC", "admin"}
        is_privileged = groups and any(group in groups for group in privileged_groups)
        license_type = None if is_privileged else "BY-C"
        return query_operator.query(license=license_type)
