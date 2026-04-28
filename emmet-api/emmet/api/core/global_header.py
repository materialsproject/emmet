from fastapi import Response, Request
from typing import Any

from emmet.api.resource.core import HeaderProcessor
from emmet.api.utils import STORE_PARAMS
from emmet.api.routes.materials.materials.query_operators import LicenseQuery


def _get_header_key(headers: Request.headers, key: str, default: Any = None) -> Any:
    """Get a case-insensitive key from a set of request headers."""
    try:
        return next(v for k, v in headers.items() if k.lower() == key.lower())
    except StopIteration:
        return default


class GlobalHeaderProcessor(HeaderProcessor):

    def process_header(self, response: Response, request: Request) -> None:
        if (
            groups := _get_header_key(request.headers, "x-authenticated-groups")
        ) is not None and "api_all_nolimit" in [
            group.strip() for group in groups.split(",")
        ]:
            response.headers["X-Bypass-Rate-Limit"] = "ALL"

        # forward Consumer Id header in response
        consumer_id = _get_header_key(request.headers, "x-consumer-id", default="-")
        response.headers["X-Consumer-Id"] = consumer_id

        if _get_header_key(response.headers, "Content-Type") is None:
            response.headers["Content-Type"] = "application/json"

    def configure_query_on_request(
        self, request: Request, query_operator: LicenseQuery
    ) -> STORE_PARAMS:

        if not (
            groups := _get_header_key(
                request.headers,
                "x-consumer-groups",
                default=_get_header_key(
                    request.headers, "x-authenticated-groups", default=""
                ),
            )
        ):
            return query_operator.query(license="BY-C")

        return query_operator.query(
            license=(
                "All"
                if {group.strip() for group in groups.split(",")}
                & {"TERMS:ACCEPT-NC", "admin"}
                else "BY-C"
            )
        )
