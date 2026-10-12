"""Log formatters: Datadog-friendly JSON for deployments, readable text for dev.

Adapted from `mp_ui.core.logging.formatters` (MP frontend), which is itself
based on the dagster pipelines' `common.logging.formatters`.

Every attribute on a record that isn't a builtin `LogRecord` attribute is
emitted as a field. That includes `extra=` fields, the request context added
by `RequestContextFilter`, and the `dd.*` trace-correlation attributes ddtrace
adds when `DD_LOGS_INJECTION=true`.

Access-log records are turned into Datadog's standard HTTP attributes:

- gunicorn (`gunicorn.access`) and `mp_logging.asgi` (`asgi.access`) log each
  request as `logger.info(format, atoms)`, with gunicorn's atom names
- tornado (`tornado.access`, e.g. the Jupyter kernel gateway) logs
  `"%d %s %.2fms"` with (status, "METHOD URI (IP)", milliseconds)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from collections.abc import Mapping
from typing import Any

# Attributes every LogRecord has. Anything else on a record is a structured field.
# These names also can't be used as `extra=` keys (logging raises KeyError).
LOG_RECORD_BUILTIN_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)

GUNICORN_ACCESS_LOGGER = "gunicorn.access"
ASGI_ACCESS_LOGGER = "asgi.access"
TORNADO_ACCESS_LOGGER = "tornado.access"
# Loggers whose records carry gunicorn-style access atoms
ATOM_ACCESS_LOGGERS = frozenset({GUNICORN_ACCESS_LOGGER, ASGI_ACCESS_LOGGER})

# Same patterns as the "Parse URL Path root" / "First two elements from URL
# Path" grok parsers of the previous Datadog pipeline, so facets keep their values:
#   /materials/summary/mp-149 -> path_root "/materials", path_first_two "/materials/summary"
_PATH_ROOT = re.compile(r"([^/]*/){1}[^/]+")
_PATH_FIRST_TWO = re.compile(r"([^/]*/){2}[^/]+")

# tornado.web.RequestHandler._request_summary(): "GET /api/kernels (127.0.0.1)"
_TORNADO_SUMMARY = re.compile(r"^(?P<method>\S+) (?P<uri>\S+) \((?P<ip>[^)]*)\)$")


def path_fields(path: str | None) -> dict[str, str]:
    """`http.url_details.path_root` / `path_first_two` for a URL path (if they exist)."""
    fields: dict[str, str] = {}
    if not path:
        return fields
    if match := _PATH_ROOT.match(path):
        fields["http.url_details.path_root"] = match.group(0)
    if match := _PATH_FIRST_TWO.match(path):
        fields["http.url_details.path_first_two"] = match.group(0)
    return fields


def status_category(status: int | None) -> str | None:
    """Datadog status for an HTTP status code: info (1xx-3xx), warning (4xx), error (5xx)."""
    if status is None:
        return None
    if status >= 500:
        return "error"
    if status >= 400:
        return "warning"
    return "info"


# `level` given to access records, by status category
_ACCESS_LEVELS = {"info": "INFO", "warning": "WARNING", "error": "ERROR"}


def process_name() -> str | None:
    """The supervisor program this process runs under (e.g. contribs-api), if any."""
    return os.environ.get("SUPERVISOR_PROCESS_NAME") or None


def _atom(atoms: Mapping[str, Any], key: str) -> Any:
    """An access-log atom, or None if it's missing or "-"."""
    try:
        value = atoms[key]
    except KeyError:
        return None
    return None if value in ("-", "", None) else value


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _client(atoms: Mapping[str, Any]) -> tuple[Any, int | None]:
    """Client IP and port. gunicorn gives the port as an environ atom;
    the ASGI middleware gives it as its own atom."""
    ip = _atom(atoms, "h")
    port = _as_int(_atom(atoms, "{remote_port}e"))
    return ip, port


def _http_fields(
    *,
    method: Any,
    path: Any,
    query: Any,
    status: int | None,
    duration_ns: int | None,
) -> dict[str, Any]:
    category = status_category(status)
    return {
        # Access records take their level from the response status, so 4xx/5xx
        # responses show as warnings/errors
        "level": _ACCESS_LEVELS.get(category) if category else None,
        "http.method": method,
        # Full URL for a Datadog URL parser, which fills `http.url_details`
        # (including `queryString` as an object of parameters)
        "http.url": f"{path}?{query}" if query else path,
        "http.url_details.path": path,
        **path_fields(path),
        "http.status_code": status,
        "http.status_category": category,
        # Datadog's standard duration attribute is in nanoseconds
        "duration": duration_ns,
    }


def _atom_access_fields(atoms: Mapping[str, Any]) -> dict[str, Any]:
    method = _atom(atoms, "m")
    path = _atom(atoms, "U")
    status = _as_int(_atom(atoms, "s"))
    duration_us = _as_int(_atom(atoms, "D"))
    ip, port = _client(atoms)
    return {
        "message": f"{method} {path} {status}",
        **_http_fields(
            method=method,
            path=path,
            query=_atom(atoms, "q"),
            status=status,
            duration_ns=duration_us * 1000 if duration_us is not None else None,
        ),
        "http.version": _atom(atoms, "H"),
        "http.referer": _atom(atoms, "f"),
        "http.useragent": _atom(atoms, "a"),
        "http.request_id": _atom(atoms, "{x-request-id}i")
        or _atom(atoms, "{kong-request-id}i"),
        "network.client.ip": ip,
        "network.client.port": port,
        "network.bytes_written": _as_int(_atom(atoms, "B")),
        # Kong consumer, as forwarded by the gateway
        "usr.id": _atom(atoms, "{x-consumer-id}i"),
        "usr.groups": _atom(atoms, "{x-consumer-groups}o")
        or _atom(atoms, "{x-consumer-groups}i")
        or _atom(atoms, "{x-authenticated-groups}i"),
        # Dash callback name (web only; absent for APIs)
        "dash.callback": _atom(atoms, "{x-callback-name}o"),
        "process.pid": _as_int(str(_atom(atoms, "p") or "").strip("<>")),
        "process.name": process_name(),
    }


def _tornado_access_fields(args: tuple[Any, ...]) -> dict[str, Any] | None:
    status, summary, ms = args
    match = _TORNADO_SUMMARY.match(str(summary))
    if match is None:
        return None
    method, uri, ip = match.group("method", "uri", "ip")
    path, _, query = uri.partition("?")
    status = _as_int(status)
    try:
        duration_ns = int(float(ms) * 1_000_000)
    except (TypeError, ValueError):
        duration_ns = None
    return {
        "message": f"{method} {path} {status}",
        **_http_fields(
            method=method,
            path=path,
            query=query,
            status=status,
            duration_ns=duration_ns,
        ),
        "network.client.ip": ip or None,
        "process.name": process_name(),
    }


def access_log_fields(record: logging.LogRecord) -> dict[str, Any] | None:
    """Structured fields for an access-log record.

    Field names follow Datadog's standard attributes so its HTTP facets work
    without remapping.

    Returns:
        dict of fields (including "message"), or None if `record` isn't an
        access-log record.
    """
    fields: dict[str, Any] | None = None
    if record.name in ATOM_ACCESS_LOGGERS and isinstance(record.args, Mapping):
        fields = _atom_access_fields(record.args)
    elif (
        record.name == TORNADO_ACCESS_LOGGER
        and isinstance(record.args, tuple)
        and len(record.args) == 3
    ):
        fields = _tornado_access_fields(record.args)
    if fields is None:
        return None
    return {k: v for k, v in fields.items() if v is not None}


# Attributes some frameworks add to their records, renamed to Datadog's
# standard attributes (e.g. Django's `django.request` / `django.server`)
_RENAMED_ATTRS = {"status_code": "http.status_code"}
# Attributes some frameworks add that aren't useful as fields (Django's
# request/server objects, whose useful parts are already in the request
# context; uvicorn's ANSI-colored copy of the message)
_DROPPED_ATTRS = frozenset({"request", "server_time", "color_message"})


def extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Non-builtin attributes of a record (`extra=`, filters, ddtrace)."""
    return {
        _RENAMED_ATTRS.get(key, key): val
        for key, val in record.__dict__.items()
        if key not in LOG_RECORD_BUILTIN_ATTRS and key not in _DROPPED_ATTRS
    }


class DatadogStructuredFormatter(logging.Formatter):
    """One JSON object per record, using Datadog's standard attribute names."""

    def __init__(self, *, fmt_keys: dict[str, str] | None = None) -> None:
        """Create the formatter.

        Args:
            fmt_keys (dict or None) : output key -> LogRecord attribute, or
                "message" / "timestamp" for the formatted message and the
                ISO-8601 UTC time.
        """
        super().__init__()
        self.fmt_keys = fmt_keys if fmt_keys is not None else {}

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(self._prepare_log_dict(record), default=str)

    def _prepare_log_dict(self, record: logging.LogRecord) -> dict[str, Any]:
        access = access_log_fields(record)
        always_fields: dict[str, Any] = {
            "message": (
                access.pop("message")
                if access is not None
                else record.getMessage().rstrip()
            ),
            "timestamp": dt.datetime.fromtimestamp(
                record.created, tz=dt.timezone.utc
            ).isoformat(),
        }

        # `exc_info` is (None, None, None) when `logger.exception` is called
        # outside an `except` block
        if record.exc_info and record.exc_info[0] is not None:
            exc_type, exc_value, _ = record.exc_info
            # Datadog's standard error attributes
            always_fields["error.kind"] = exc_type.__name__
            always_fields["error.message"] = str(exc_value)
            always_fields["error.stack"] = self.formatException(record.exc_info)

        # Only present when a call site passes `stack_info=True`
        if record.stack_info is not None:
            always_fields["error.stack_info"] = self.formatStack(record.stack_info)

        message = {
            key: (
                msg_val
                if (msg_val := always_fields.pop(attr, None)) is not None
                else getattr(record, attr, None)
            )
            for key, attr in self.fmt_keys.items()
        }
        message.update(always_fields)
        if access is not None:
            message.update(access)
        message.update(extra_fields(record))
        return message


class ConsoleFormatter(logging.Formatter):
    """Readable single-line records for local development.

    `2026-10-08 12:00:00,000 WARNING  [mpcontribs.api] Message  key=value ...`
    """

    def __init__(
        self,
        fmt: str = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt: str | None = None,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        access = access_log_fields(record)
        if access is not None:
            # Format a copy, so other handlers still see the original record
            record = logging.makeLogRecord(record.__dict__)
            record.msg, record.args = access.pop("message"), None
            if level := access.pop("level", None):
                record.levelname = level
        text = super().format(record)

        fields = {**(access or {}), **extra_fields(record)}
        # ddtrace's injected ids are noise locally
        fields = {
            k: v for k, v in fields.items() if not k.startswith("dd.") and v is not None
        }
        if fields:
            pairs = " ".join(f"{k}={v}" for k, v in fields.items())
            first, sep, rest = text.partition("\n")
            text = f"{first}  {pairs}{sep}{rest}"
        return text
