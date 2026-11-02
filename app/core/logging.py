"""Structured logging configuration.

LeaseLens is privacy-by-design: extracted lease text must never reach the logs.
Anything user-supplied is logged only as a length/prefix-free identifier, and
``log_raw_text`` must stay ``False`` in production.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


class _JsonFormatter(logging.Formatter):
    """Minimal dependency-free JSON formatter for production logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "request_id": _request_id.get(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


class _HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        prefix = f"{record.levelname:<8} {record.name:<28} [{_request_id.get()}]"
        text = f"{prefix} {record.getMessage()}"
        if record.exc_info:
            text = f"{text}\n{self.formatException(record.exc_info)}"
        extras = getattr(record, "extra_fields", {})
        if extras:
            text = f"{text} | {' '.join(f'{k}={v}' for k, v in extras.items())}"
        return text


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    """Install a single stdout handler with the requested formatter."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter() if json_logs else _HumanFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn keeps its own handlers; route them through ours.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # httpx logs full URLs (never bodies) at INFO - keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    **fields: Any,
) -> None:
    """Emit a log record carrying structured fields."""
    if not logger.isEnabledFor(level):
        return
    logger.log(level, message, extra={"extra_fields": fields})


def configure_for_tests() -> None:
    configure_logging("WARNING", json_logs=False)
