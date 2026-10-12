"""`logging.config.dictConfig` configuration shared by MP backend processes."""

from __future__ import annotations

import copy
import logging
import logging.config
import os
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from .formatters import (
    ASGI_ACCESS_LOGGER,
    GUNICORN_ACCESS_LOGGER,
    TORNADO_ACCESS_LOGGER,
)

LogFormat = Literal["json", "console"]

# Names are prefixed so they don't clash with the names other tools use when
# this config is merged into theirs (e.g. traitlets' "console" formatter)
HANDLER = "mp_stderr"

# This package's import path (it is copied into each service's own package)
_PKG = __name__.rsplit(".", 1)[0]

# Loggers that write access logs: always INFO, straight to the handler
ACCESS_LOGGERS = (GUNICORN_ACCESS_LOGGER, ASGI_ACCESS_LOGGER)

# output key: LogRecord attribute (or "message" / "timestamp")
FMT_KEYS = {
    "level": "levelname",
    "message": "message",
    "timestamp": "timestamp",
    "logger.name": "name",
    "logger.module": "module",
    "logger.function": "funcName",
    "logger.line": "lineno",
    "logger.thread_name": "threadName",
    "process.pid": "process",
}

_BASE_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {"()": f"{_PKG}.context.RequestContextFilter"},
    },
    "formatters": {
        "mp_json": {
            "()": f"{_PKG}.formatters.DatadogStructuredFormatter",
            "fmt_keys": FMT_KEYS,
        },
        "mp_console": {"()": f"{_PKG}.formatters.ConsoleFormatter"},
    },
    "handlers": {
        "mp_stderr": {
            "class": "logging.StreamHandler",
            "formatter": "mp_json",
            "filters": ["request_context"],
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        # gunicorn's (and uvicorn's) own loggers don't propagate, so they need
        # the handler directly
        "gunicorn.error": {"level": "INFO", "handlers": [HANDLER], "propagate": False},
        "uvicorn.error": {"level": "INFO", "handlers": [HANDLER], "propagate": False},
    },
    # Everything else (third-party libraries, captured warnings):
    # WARNING and up (overridable with MP_LOG_LEVEL)
    "root": {"level": "WARNING", "handlers": [HANDLER]},
}


def _level_name(level: int | str) -> str:
    if isinstance(level, int):
        return logging.getLevelName(level)
    name = level.strip().upper()
    if name == "WARN":
        name = "WARNING"
    if not isinstance(logging.getLevelName(name), int):
        raise ValueError(f"Unknown log level {repr(level)}")
    return name


def build_logging_config(
    *,
    app_loggers: Iterable[str] = (),
    access_loggers: Iterable[str] = ACCESS_LOGGERS,
    extra_loggers: Mapping[str, Mapping[str, Any]] | None = None,
    fmt: LogFormat | None = None,
    level: int | str | None = None,
    app_level: int | str | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    """The `logging.config.dictConfig` dict for a service.

    Arguments left as None come from env vars.

    Args:
        app_loggers : the service's own loggers (e.g. "mpcontribs"), logged at
            `app_level` instead of the root level
        access_loggers : loggers that write access logs (INFO, not propagated)
        extra_loggers : extra per-logger config, applied last
        fmt : "json" or "console" (`MP_LOG_FORMAT`, default "json")
        level : root level (`MP_LOG_LEVEL`, default WARNING)
        app_level : level for `app_loggers` (`MP_APP_LOG_LEVEL`, default
            INFO, or DEBUG if `debug`)
        debug : log the service's own loggers at DEBUG unless `app_level`
            is set

    Returns:
        dict for `logging.config.dictConfig` (a fresh copy, safe to modify)
    """
    fmt = fmt or os.environ.get("MP_LOG_FORMAT") or "json"  # type: ignore[assignment]
    if fmt not in ("json", "console"):
        raise ValueError(
            f"Unknown log format {repr(fmt)}, expected 'json' or 'console'"
        )
    level = _level_name(level or os.environ.get("MP_LOG_LEVEL") or "WARNING")
    app_level = _level_name(
        app_level
        or os.environ.get("MP_APP_LOG_LEVEL")
        or ("DEBUG" if debug else "INFO")
    )

    config = copy.deepcopy(_BASE_CONFIG)
    config["handlers"][HANDLER]["formatter"] = f"mp_{fmt}"
    config["root"]["level"] = level
    loggers = config["loggers"]
    for name in access_loggers:
        loggers[name] = {"level": "INFO", "handlers": [HANDLER], "propagate": False}
    for name in app_loggers:
        loggers.setdefault(name, {})["level"] = app_level
    for name, overrides in (extra_loggers or {}).items():
        loggers.setdefault(name, {}).update(copy.deepcopy(dict(overrides)))
    return config


def configure_logging(**kwargs: Any) -> dict[str, Any]:
    """Configure logging for the process. Safe to call more than once.

    Python warnings are captured into the `py.warnings` logger, so they are
    formatted like everything else. See `build_logging_config` for the
    arguments.

    Returns:
        the applied config
    """
    config = build_logging_config(**kwargs)
    logging.config.dictConfig(config)
    logging.captureWarnings(True)
    return config


def gunicorn_logconfig_dict(**kwargs: Any) -> dict[str, Any]:
    """Config for gunicorn's `logconfig_dict` setting (in `gunicorn.conf.py`).

    Applied by gunicorn in the master before forking, so gunicorn's own error
    and access logs use the same handlers and formatters as the application.
    Only imports this package, not the application.
    """
    return build_logging_config(**kwargs)


__all__ = [
    "ACCESS_LOGGERS",
    "FMT_KEYS",
    "HANDLER",
    "TORNADO_ACCESS_LOGGER",
    "build_logging_config",
    "configure_logging",
    "gunicorn_logconfig_dict",
]
