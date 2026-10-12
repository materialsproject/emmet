"""Per-request logging context, independent of the web framework.

Framework glue (`flask_ext`, `django_ext`, `asgi`) binds the current
request's fields with `bind_request_context` at the start of a request and
resets them at the end. `RequestContextFilter` adds them to every record
logged meanwhile, including records from libraries.

The context is a `contextvars.ContextVar`, so it is per-greenlet under gevent
and per-task under asyncio.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from contextvars import ContextVar, Token
from typing import Any

from .formatters import path_fields, process_name

_REQUEST_CONTEXT: ContextVar[Mapping[str, Any] | None] = ContextVar(
    "mp_logging_request_context", default=None
)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """A request header from a case-insensitive or lower-cased mapping."""
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    return value or None


def request_fields(
    method: str | None, path: str | None, headers: Mapping[str, str]
) -> dict[str, Any]:
    """Fields describing a request, from its method, path and headers.

    The Kong gateway forwards the consumer in `X-Consumer-Id` and the request
    id in `Kong-Request-Id` (or `X-Request-Id` if set upstream).
    """
    fields = {
        "http.method": method,
        "http.url_details.path": path,
        **path_fields(path),
        "usr.id": _header(headers, "X-Consumer-Id"),
        "http.request_id": _header(headers, "X-Request-Id")
        or _header(headers, "Kong-Request-Id"),
    }
    return {k: v for k, v in fields.items() if v}


def bind_request_context(fields: Mapping[str, Any]) -> Token:
    """Set the current request's fields. Pass the token to `reset_request_context`."""
    return _REQUEST_CONTEXT.set(dict(fields))


def reset_request_context(token: Token | None) -> None:
    """Restore the context from before `bind_request_context`. Never raises."""
    if token is None:
        return
    try:
        _REQUEST_CONTEXT.reset(token)
    except (ValueError, RuntimeError):
        # Token from another context (e.g. teardown ran elsewhere): just clear
        _REQUEST_CONTEXT.set(None)


def get_request_context() -> Mapping[str, Any] | None:
    """The current request's fields, or None outside a request."""
    return _REQUEST_CONTEXT.get()


class RequestContextFilter(logging.Filter):
    """Add the process name, and the current request's context, to every record.

    Attached to handlers (not loggers), so it also applies to records from
    libraries that reach the service's handlers. Outside a request (startup,
    background work) records only get the process name. Never drops a record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # The supervisor program (e.g. contribs-api, micro-worker), on every record
        if not hasattr(record, "process.name") and (name := process_name()):
            setattr(record, "process.name", name)
        context = _REQUEST_CONTEXT.get()
        if not context:
            return True
        for key, value in context.items():
            # Fields set explicitly at the call site win
            if not hasattr(record, key):
                setattr(record, key, value)
        return True
