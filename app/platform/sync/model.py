from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.platform.modules.model import validate_module_id

SYNC_PROTOCOL_VERSION = "1"

_TECHNICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def validate_stream_id(stream_id: str) -> None:
    if not isinstance(stream_id, str) or not _TECHNICAL_ID_RE.fullmatch(stream_id):
        raise ValueError("stream_id must match ^[a-z][a-z0-9_]{0,63}$")


def validate_entity_type(entity_type: str) -> None:
    if not isinstance(entity_type, str) or not _TECHNICAL_ID_RE.fullmatch(entity_type):
        raise ValueError("entity_type must match ^[a-z][a-z0-9_]{0,63}$")


def validate_schema_version(schema_version: str) -> None:
    if not isinstance(schema_version, str):
        raise TypeError("schema_version must be a string")
    if not schema_version.strip():
        raise ValueError("schema_version cannot be blank")
    if len(schema_version) > 64:
        raise ValueError("schema_version cannot exceed 64 characters")


def validate_protocol_version(protocol_version: str) -> None:
    if not isinstance(protocol_version, str):
        raise TypeError("sync_protocol_version must be a string")
    if not protocol_version.strip():
        raise ValueError("sync_protocol_version cannot be blank")
    if len(protocol_version) > 32:
        raise ValueError("sync_protocol_version cannot exceed 32 characters")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class SyncChangeKind(StrEnum):
    UPSERT = "UPSERT"
    TOMBSTONE = "TOMBSTONE"


@dataclass(frozen=True, slots=True)
class SyncChange:
    entity_type: str
    entity_id: UUID
    change_kind: SyncChangeKind
    schema_version: str
    payload: Mapping[str, object] | None
    entity_version: int | None = None

    def __post_init__(self) -> None:
        validate_entity_type(self.entity_type)
        if not isinstance(self.entity_id, UUID):
            raise TypeError("entity_id must be a UUID")
        if not isinstance(self.change_kind, SyncChangeKind):
            raise TypeError("change_kind must be a SyncChangeKind")
        validate_schema_version(self.schema_version)
        if self.entity_version is not None:
            if not isinstance(self.entity_version, int) or isinstance(
                self.entity_version, bool
            ):
                raise TypeError("entity_version must be an int or None")
            if self.entity_version < 1:
                raise ValueError("entity_version must be positive when present")
        if self.payload is not None and not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping or None")
        if self.change_kind is SyncChangeKind.UPSERT and self.payload is None:
            raise ValueError("UPSERT requires a complete projection payload")


@dataclass(frozen=True, slots=True)
class SyncBatch:
    batch_id: UUID
    company_id: UUID
    module_id: str
    stream_id: str
    position: int
    sync_protocol_version: str
    recorded_at: datetime
    changes: tuple[SyncChange, ...]
    source_command_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.batch_id, UUID):
            raise TypeError("batch_id must be a UUID")
        if not isinstance(self.company_id, UUID):
            raise TypeError("company_id must be a UUID")
        validate_module_id(self.module_id)
        validate_stream_id(self.stream_id)
        if not isinstance(self.position, int) or isinstance(self.position, bool):
            raise TypeError("position must be an int")
        if self.position < 1:
            raise ValueError("position must be positive")
        validate_protocol_version(self.sync_protocol_version)
        _require_aware(self.recorded_at, "recorded_at")
        if not isinstance(self.changes, tuple):
            raise TypeError("changes must be a tuple")
        if not self.changes:
            raise ValueError("SyncBatch cannot be empty")
        if not all(isinstance(change, SyncChange) for change in self.changes):
            raise TypeError("changes must contain only SyncChange values")
        if self.source_command_id is not None and not isinstance(
            self.source_command_id, UUID
        ):
            raise TypeError("source_command_id must be a UUID or None")


@dataclass(frozen=True, slots=True)
class SyncProjection:
    entity_type: str
    entity_id: UUID
    schema_version: str
    payload: Mapping[str, object]
    entity_version: int | None = None

    def __post_init__(self) -> None:
        validate_entity_type(self.entity_type)
        if not isinstance(self.entity_id, UUID):
            raise TypeError("entity_id must be a UUID")
        validate_schema_version(self.schema_version)
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        if self.entity_version is not None:
            if not isinstance(self.entity_version, int) or isinstance(
                self.entity_version, bool
            ):
                raise TypeError("entity_version must be an int or None")
            if self.entity_version < 1:
                raise ValueError("entity_version must be positive when present")


@dataclass(frozen=True, slots=True)
class BootstrapPage:
    items: tuple[SyncProjection, ...]
    next_key: str | None
    has_more: bool

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        if not all(isinstance(item, SyncProjection) for item in self.items):
            raise TypeError("items must contain only SyncProjection values")
        if not isinstance(self.has_more, bool):
            raise TypeError("has_more must be a bool")
        if self.next_key is not None:
            if not isinstance(self.next_key, str):
                raise TypeError("next_key must be a string or None")
            if not self.next_key:
                raise ValueError("next_key cannot be blank")
        if self.has_more and self.next_key is None:
            raise ValueError("has_more requires next_key")
        if not self.has_more and self.next_key is not None:
            raise ValueError("final bootstrap page cannot expose next_key")
