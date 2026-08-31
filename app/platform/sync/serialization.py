from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from app.platform.sync.model import SyncChange, SyncChangeKind


def _json_native(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        # json.dumps(..., allow_nan=False) performs the finite-value check.
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Sync payload mapping keys must be strings")
            normalized[key] = _json_native(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_native(item) for item in value]
    raise TypeError(
        "Sync payload values must already be JSON-native; "
        f"unsupported type: {type(value).__name__}"
    )


def normalize_payload(payload: Mapping[str, object] | None) -> dict[str, object] | None:
    if payload is None:
        return None
    normalized = _json_native(payload)
    if not isinstance(normalized, dict):
        raise TypeError("Sync payload must normalize to a JSON object")
    # Round-trip validation provides a detached, immutable-by-convention snapshot
    # for persistence and rejects NaN/Infinity.
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    loaded = json.loads(encoded)
    assert isinstance(loaded, dict)
    return loaded


def change_to_document(change: SyncChange) -> dict[str, object]:
    return {
        "entity_type": change.entity_type,
        "entity_id": str(change.entity_id),
        "change_kind": change.change_kind.value,
        "schema_version": change.schema_version,
        "entity_version": change.entity_version,
        "payload": normalize_payload(change.payload),
    }


def changes_to_document(changes: tuple[SyncChange, ...]) -> list[dict[str, object]]:
    return [change_to_document(change) for change in changes]


def serialized_changes_size(changes: tuple[SyncChange, ...]) -> int:
    document = changes_to_document(changes)
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return len(encoded)


def change_from_document(document: Mapping[str, Any]) -> SyncChange:
    payload = document.get("payload")
    if payload is not None and not isinstance(payload, Mapping):
        raise ValueError("persisted Sync payload is not a JSON object")
    entity_version = document.get("entity_version")
    return SyncChange(
        entity_type=str(document["entity_type"]),
        entity_id=UUID(str(document["entity_id"])),
        change_kind=SyncChangeKind(str(document["change_kind"])),
        schema_version=str(document["schema_version"]),
        entity_version=(int(entity_version) if entity_version is not None else None),
        payload=(dict(payload) if payload is not None else None),
    )


def changes_from_document(values: object) -> tuple[SyncChange, ...]:
    if not isinstance(values, list):
        raise ValueError("persisted Sync changes_json must be a JSON array")
    changes: list[SyncChange] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("persisted Sync change must be a JSON object")
        changes.append(change_from_document(value))
    return tuple(changes)
