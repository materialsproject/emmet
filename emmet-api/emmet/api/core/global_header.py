from maggma.api.resource.core import HeaderProcessor
from fastapi import Response, Request


class GlobalHeaderProcessor(HeaderProcessor):
    def process_header(self, response: Response, request: Request):
        groups = request.headers.get("X-Authenticated-Groups", None)
        if groups is not None:
            if "staff" in groups:
                response.headers["X-Bypass-Rate-Limit"] = "ALL"
