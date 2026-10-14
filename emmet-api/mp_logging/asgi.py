"""Request logging context and access log for ASGI apps (FastAPI, Starlette).

Under gunicorn's `UvicornWorker`, gunicorn's own access log isn't used, so
this middleware writes it: one record per request on the `asgi.access`
logger, with the same atoms as gunicorn's access log, so the formatters turn
both into the same fields.

```python
app.add_middleware(LoggingMiddleware)  # add last, so it wraps the other middleware
```
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from .context import (
    bind_request_context,
    request_fields,
    reset_request_context,
)
from .formatters import ASGI_ACCESS_LOGGER, ROUTE_ATOM

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# Fallback text (ConsoleFormatter / plain handlers); the formatters build the
# message and fields from the atoms
ACCESS_LOG_FORMAT = '%(h)s %(m)s %(U)s?%(q)s %(H)s %(s)s %(B)s "%(f)s" "%(a)s" %(D)s'


def _decode_headers(raw: Any) -> dict[str, str]:
    return {
        name.decode("latin1").lower(): value.decode("latin1")
        for name, value in raw or ()
    }


def _route_template(scope: Scope) -> str | None:
    """The full path template of the route that handled the request.

    FastAPI (>= 0.139) keeps routes of included routers un-prefixed in
    `scope["route"]` and records the effective route, with the router
    prefixes, in its own scope entry; prefer that. Plain Starlette: the route
    in the scope (its router stores it in the shared scope once matched).
    """
    context = (scope.get("fastapi") or {}).get("effective_route_context")
    path = getattr(context, "path", None)
    if not isinstance(path, str) or not path:
        path = getattr(scope.get("route"), "path", None)
    if not isinstance(path, str) or not path:
        return None
    # Mounted sub-apps: the mount prefix is in root_path
    return scope.get("root_path", "") + path


class _Atoms(dict):
    """Access-log atoms; missing ones format as "-" (like gunicorn's)."""

    def __missing__(self, key: str) -> str:
        return "-"


def _atoms(
    scope: Scope,
    request_headers: dict[str, str],
    response_headers: dict[str, str],
    status: int,
    duration_s: float,
) -> _Atoms:
    client = scope.get("client") or (None, None)
    atoms = _Atoms(
        {
            "h": client[0] or "-",
            "{remote_port}e": client[1] if client[1] is not None else "-",
            "m": scope.get("method", "-"),
            "U": scope.get("root_path", "") + scope.get("path", ""),
            "q": (scope.get("query_string") or b"").decode("latin1"),
            "H": f"HTTP/{scope.get('http_version', '1.1')}",
            "s": status,
            "B": response_headers.get("content-length", "-"),
            "f": request_headers.get("referer", "-"),
            "a": request_headers.get("user-agent", "-"),
            "D": int(duration_s * 1_000_000),
            "p": f"<{os.getpid()}>",
            # Matched route template; Starlette's router stores the route in
            # the (shared) scope, so it's there once the app has run
            ROUTE_ATOM: _route_template(scope) or "-",
        }
    )
    atoms.update({f"{{{k}}}i": v for k, v in request_headers.items()})
    atoms.update({f"{{{k}}}o": v for k, v in response_headers.items()})
    return atoms


class LoggingMiddleware:
    """Bind the request's logging context, and write an access record per request."""

    def __init__(
        self,
        app: ASGIApp,
        logger: logging.Logger | None = None,
        exclude_paths: tuple[str, ...] = (),
    ) -> None:
        """
        Args:
            app : the ASGI app
            logger : access logger (default `asgi.access`)
            exclude_paths : paths that get no access record (e.g. healthchecks)
        """
        self.app = app
        self.logger = logger or logging.getLogger(ASGI_ACCESS_LOGGER)
        self.exclude_paths = frozenset(exclude_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = _decode_headers(scope.get("headers"))
        path = scope.get("root_path", "") + scope.get("path", "")
        token = bind_request_context(
            request_fields(scope.get("method"), path, request_headers)
        )
        response: dict[str, Any] = {"status": 500, "headers": {}}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
                response["headers"] = _decode_headers(message.get("headers"))
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            if path not in self.exclude_paths:
                try:
                    self.logger.info(
                        ACCESS_LOG_FORMAT,
                        _atoms(
                            scope,
                            request_headers,
                            response["headers"],
                            response["status"],
                            duration,
                        ),
                    )
                except Exception:  # logging must never break a request
                    pass
            reset_request_context(token)
