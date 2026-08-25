from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.platform.commands.model import CommandContext


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite decimals are not supported")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _canonical_value(value: object) -> object:
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, Decimal):
        return ["decimal", _decimal_text(value)]
    if isinstance(value, UUID):
        return ["uuid", str(value)]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime values must be timezone-aware")
        normalized = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return ["datetime", normalized]
    if isinstance(value, float):
        raise TypeError("float payload values are not supported; normalize decimals explicitly")
    if isinstance(value, Mapping):
        items: list[list[object]] = []
        for key in sorted(value):
            if not isinstance(key, str):
                raise TypeError("payload mapping keys must be strings")
            items.append([key, _canonical_value(value[key])])
        return ["map", items]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return ["list", [_canonical_value(item) for item in value]]
    raise TypeError(f"unsupported payload type: {type(value).__name__}")


def canonical_command_document(
    context: CommandContext,
    payload: Mapping[str, object],
) -> str:
    document = {
        "command_name": context.command_name,
        "command_schema_version": context.command_schema_version,
        "scope": context.scope.value,
        "tenant_id": str(context.tenant_id),
        "company_id": str(context.company_id) if context.company_id else None,
        "actor_user_id": str(context.actor_user_id),
        "expected_version": context.expected_version,
        "payload": _canonical_value(payload),
    }
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def command_fingerprint(
    context: CommandContext,
    payload: Mapping[str, object],
) -> str:
    canonical = canonical_command_document(context, payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
