from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.platform.modules.model import validate_module_id
from app.platform.sync.errors import sync_batch_too_large
from app.platform.sync.model import (
    SYNC_PROTOCOL_VERSION,
    SyncBatch,
    SyncChange,
    validate_stream_id,
)
from app.platform.sync.repository import SyncJournalRepository
from app.platform.sync.serialization import serialized_changes_size


logger = logging.getLogger(__name__)
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class SyncPublisher:
    """Append Sync changes inside the caller's active Tenant transaction.

    The publisher deliberately owns no TransactionBoundary. If it is called
    outside an active Tenant transaction, the repository/session scope fails
    closed. This preserves BE-DES-007's business + P-4 + Sync single-COMMIT
    invariant for bounded-context integrations.
    """

    def __init__(
        self,
        repository: SyncJournalRepository,
        *,
        max_batch_bytes: int,
        clock: Clock = _utc_now,
    ) -> None:
        if max_batch_bytes <= 0:
            raise ValueError("max_batch_bytes must be positive")
        self._repository = repository
        self._max_batch_bytes = max_batch_bytes
        self._clock = clock

    def publish(
        self,
        *,
        company_id: UUID,
        module_id: str,
        stream_id: str,
        changes: tuple[SyncChange, ...],
        source_command_id: UUID | None = None,
    ) -> SyncBatch:
        # Validate the complete public publisher contract before touching the
        # active SQLAlchemy Session. A malformed bounded-context integration must
        # fail closed without materializing a stream or consuming a position.
        if not isinstance(company_id, UUID):
            raise TypeError("company_id must be a UUID")
        validate_module_id(module_id)
        validate_stream_id(stream_id)
        if not isinstance(changes, tuple):
            raise TypeError("changes must be a tuple")
        if not changes:
            raise ValueError("Sync publish requires at least one change")
        if not all(isinstance(change, SyncChange) for change in changes):
            raise TypeError("changes must contain only SyncChange values")
        if source_command_id is not None and not isinstance(source_command_id, UUID):
            raise TypeError("source_command_id must be a UUID or None")

        batch_bytes = serialized_changes_size(changes)
        batch_id = uuid4()
        audit_fields: dict[str, object] = {
            "batch_id": str(batch_id),
            "company_id": str(company_id),
            "module_id": module_id,
            "stream_id": stream_id,
            "sync_protocol_version": SYNC_PROTOCOL_VERSION,
            "change_count": len(changes),
            "batch_bytes": batch_bytes,
        }
        if source_command_id is not None:
            audit_fields["command_id"] = str(source_command_id)

        if batch_bytes > self._max_batch_bytes:
            logger.warning(
                "sync_batch_rejected",
                extra={
                    **audit_fields,
                    "outcome": "REJECTED",
                    "error_code": "SYNC_BATCH_TOO_LARGE",
                },
            )
            raise sync_batch_too_large()

        recorded_at = self._clock()
        _require_aware(recorded_at, "recorded_at")
        try:
            batch = self._repository.append_batch(
                batch_id=batch_id,
                company_id=company_id,
                module_id=module_id,
                stream_id=stream_id,
                sync_protocol_version=SYNC_PROTOCOL_VERSION,
                source_command_id=source_command_id,
                recorded_at=recorded_at,
                changes=changes,
            )
        except Exception as exc:
            logger.error(
                "sync_publish_failed",
                extra={
                    **audit_fields,
                    "outcome": "FAILED",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        logger.info(
            "sync_batch_published",
            extra={
                **audit_fields,
                "position": batch.position,
                "outcome": "SUCCEEDED",
            },
        )
        return batch
