"""Structured JSON logger for the extraction pipeline."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataset_extractor.config import LOG_DIR, LOG_LEVEL


def _json_serializer(obj: Any) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data  # type: ignore[attr-defined]
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return json.dumps(log_entry, default=_json_serializer)


def get_logger(name: str, log_file: str | None = None) -> logging.Logger:
    """Return a logger that writes JSON lines to *log_file* and stderr."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    fmt = JSONFormatter()

    # stderr handler
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # file handler
    if log_file:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_DIR / log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    level: str = "info",
    **data: Any,
) -> None:
    """Convenience helper — attach structured *data* to a log record."""
    record = logger.makeRecord(
        name=logger.name,
        level=getattr(logging, level.upper(), logging.INFO),
        fn="",
        lno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.extra_data = data  # type: ignore[attr-defined]
    logger.handle(record)
