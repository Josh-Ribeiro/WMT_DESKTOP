"""Persistent logging configuration for the central backend."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import DATA_DIR


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging() -> Path:
    """Write application logs to a bounded file while preserving console logs."""
    log_dir = Path(os.getenv("WMT_LOG_DIR", str(DATA_DIR / "logs")))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "backend.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(os.getenv("WMT_LOG_LEVEL", "INFO").upper())
    resolved_path = str(log_path.resolve()).lower()
    already_configured = any(
        isinstance(handler, RotatingFileHandler)
        and str(Path(handler.baseFilename).resolve()).lower() == resolved_path
        for handler in root_logger.handlers
    )
    if not already_configured:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(handler)

    return log_path
