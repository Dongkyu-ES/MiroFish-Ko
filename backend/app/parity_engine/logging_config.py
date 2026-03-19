"""Stdout logging for the parity engine."""

from __future__ import annotations

import logging
import sys


class ContextFormatter(logging.Formatter):
    """Render structured key=value fields directly to stdout/stderr."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        fields = [
            f"timestamp={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"message={record.getMessage()}",
        ]
        for key in (
            "mode",
            "route",
            "graph_id",
            "project_id",
            "simulation_id",
            "provider",
            "latency_ms",
            "result_count",
            "error_type",
            "decision",
        ):
            value = getattr(record, key, None)
            if value not in (None, ""):
                fields.append(f"{key}={value}")
        return " ".join(fields)


def configure_logging(
    logger_name: str = "mirofish.parity",
    level: str = "INFO",
    stdout_logging: bool = True,
    force: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if force:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    if stdout_logging and not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logger.level)
        handler.setFormatter(ContextFormatter())
        logger.addHandler(handler)

    return logger
