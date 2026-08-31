from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.platform.sync.model import SyncBatch, SyncChange


class SyncJournalRepository(Protocol):
    """Persistence boundary for the append-only server Sync journal.

    Every method expects to run inside an already-active Tenant transaction.
    Implementations must not open or commit an independent transaction.
    """

    def current_position(
        self,
        *,
        company_id: UUID,
        module_id: str,
        stream_id: str,
    ) -> int: ...

    def append_batch(
        self,
        *,
        batch_id: UUID,
        company_id: UUID,
        module_id: str,
        stream_id: str,
        sync_protocol_version: str,
        source_command_id: UUID | None,
        recorded_at: datetime,
        changes: tuple[SyncChange, ...],
    ) -> SyncBatch: ...

    def list_batches(
        self,
        *,
        company_id: UUID,
        module_id: str,
        stream_id: str,
        after_position: int,
        limit: int,
    ) -> tuple[SyncBatch, ...]: ...
