from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


_SAFE_EXTRA_FIELDS = (
    "correlation_id",
    "error_type",
    "error_count",
    "user_id",
    "session_id",
    "tenant_id",
    "company_id",
    "membership_id",
    "assignment_id",
    "role_id",
    "permission_id",
    "family_id",
    "status",
    "path",
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field_name in _SAFE_EXTRA_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None and value != "":
                payload[field_name] = value

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setFormatter(JsonLogFormatter())
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)
