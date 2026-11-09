"""Allowlisted JSON telemetry; free-form messages/arguments/tracebacks are never emitted."""

import json
import logging
import re
import sys
from datetime import UTC, datetime


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "component": record.name
            if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", record.name)
            else "runtime",
        }
        for name in ("event_code", "correlation_id", "event_id", "route", "method"):
            value = getattr(record, name, None)
            pattern = r"[A-Za-z0-9_./{}-]{1,150}" if name == "route" else r"[A-Za-z0-9_.:-]{1,80}"
            if isinstance(value, str) and re.fullmatch(pattern, value):
                data[name] = value
        for name in ("status", "duration_ms", "count"):
            value = getattr(record, name, None)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and 0 <= value < 10**12
            ):
                data[name] = value
        if record.exc_info and record.exc_info[0]:
            data["exception_type"] = record.exc_info[0].__name__[:80]
        return json.dumps(data, separators=(",", ":"))


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeJsonFormatter())
    for name in ("altvia", "dramatiq", "uvicorn"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        # Third-party logs must not also reach an uncontrolled root formatter.
        logger.propagate = name == "altvia"
    for name in ("uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
