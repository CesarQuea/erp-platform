from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.platform.sync.errors import sync_batch_too_large
from app.platform.sync.model import SYNC_PROTOCOL_VERSION, SyncBatch, SyncChange
from app.platform.sync.repository import SyncJournalRepository
from app.platform.sync.serialization import serialized_changes_size


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        if not changes:
            raise ValueError("Sync publish requires at least one change")
        if serialized_changes_size(changes) > self._max_batch_bytes:
            raise sync_batch_too_large()

        return self._repository.append_batch(
            batch_id=uuid4(),
            company_id=company_id,
            module_id=module_id,
            stream_id=stream_id,
            sync_protocol_version=SYNC_PROTOCOL_VERSION,
            source_command_id=source_command_id,
            recorded_at=self._clock(),
            changes=changes,
        )
