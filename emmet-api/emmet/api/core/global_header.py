from __future__ import annotations

from typing import TYPE_CHECKING

from maggma.api.resource.core import HeaderProcessor

if TYPE_CHECKING:
    from fastapi import Request, Response


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
