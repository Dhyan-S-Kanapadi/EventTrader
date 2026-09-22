"""JSON application logs; callers log static events, never payloads or credentials."""

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Deliberately omit exception text and arbitrary extra fields.
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "event": record.getMessage(),
                **{
                    key: getattr(record, key)
                    for key in ("correlation_id", "status_code", "attempt")
                    if hasattr(record, key)
                },
            }
        )


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("eventtrader")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
