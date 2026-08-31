from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.sync_models import (
    SyncBatchRecordModel,
    SyncStreamRecordModel,
)
from app.platform.sync.model import SyncBatch, SyncChange
from app.platform.sync.serialization import changes_from_document, changes_to_document


class SqlAlchemySyncJournalRepository:
    """SQLAlchemy journal using the already-active Tenant Session."""

    def __init__(self, session_scope: TenantSessionScope) -> None:
        self._session_scope = session_scope

    def current_position(
        self,
        *,
        company_id: UUID,
        module_id: str,
        stream_id: str,
    ) -> int:
        session = self._session_scope.current()
        value = session.execute(
            select(SyncStreamRecordModel.current_position).where(
                SyncStreamRecordModel.company_id == company_id,
                SyncStreamRecordModel.module_id == module_id,
                SyncStreamRecordModel.stream_id == stream_id,
            )
        ).scalar_one_or_none()
        return int(value) if value is not None else 0

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
    ) -> SyncBatch:
        session = self._session_scope.current()
        self._materialize_stream(
            company_id=company_id,
            module_id=module_id,
            stream_id=stream_id,
            recorded_at=recorded_at,
        )

        stream = session.execute(
            select(SyncStreamRecordModel)
            .where(
                SyncStreamRecordModel.company_id == company_id,
                SyncStreamRecordModel.module_id == module_id,
                SyncStreamRecordModel.stream_id == stream_id,
            )
            .with_for_update()
        ).scalar_one()

        position = int(stream.current_position) + 1
        stream.current_position = position
        stream.updated_at = recorded_at

        persisted_changes = changes_to_document(changes)
        session.add(
            SyncBatchRecordModel(
                batch_id=batch_id,
                company_id=company_id,
                module_id=module_id,
                stream_id=stream_id,
                position=position,
                sync_protocol_version=sync_protocol_version,
                source_command_id=source_command_id,
                recorded_at=recorded_at,
                changes_json=persisted_changes,
            )
        )
        # Flush here so FK/unique/serialization failures happen inside the
        # caller's transaction before P-4 can complete its result.
        session.flush()

        return SyncBatch(
            batch_id=batch_id,
            company_id=company_id,
            module_id=module_id,
            stream_id=stream_id,
            position=position,
            sync_protocol_version=sync_protocol_version,
            source_command_id=source_command_id,
            recorded_at=recorded_at,
            changes=tuple(changes),
        )

    def list_batches(
        self,
        *,
        company_id: UUID,
        module_id: str,
        stream_id: str,
        after_position: int,
        limit: int,
    ) -> tuple[SyncBatch, ...]:
        if after_position < 0:
            raise ValueError("after_position cannot be negative")
        if limit <= 0:
            raise ValueError("limit must be positive")
        session = self._session_scope.current()
        rows = session.execute(
            select(SyncBatchRecordModel)
            .where(
                SyncBatchRecordModel.company_id == company_id,
                SyncBatchRecordModel.module_id == module_id,
                SyncBatchRecordModel.stream_id == stream_id,
                SyncBatchRecordModel.position > after_position,
            )
            .order_by(SyncBatchRecordModel.position.asc())
            .limit(limit)
        ).scalars()
        return tuple(self._to_batch(row) for row in rows)

    def _materialize_stream(
        self,
        *,
        company_id: UUID,
        module_id: str,
        stream_id: str,
        recorded_at: datetime,
    ) -> None:
        session = self._session_scope.current()
        values = {
            "company_id": company_id,
            "module_id": module_id,
            "stream_id": stream_id,
            "current_position": 0,
            "created_at": recorded_at,
            "updated_at": recorded_at,
        }
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(SyncStreamRecordModel).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[
                    SyncStreamRecordModel.company_id,
                    SyncStreamRecordModel.module_id,
                    SyncStreamRecordModel.stream_id,
                ]
            )
        elif dialect == "sqlite":
            statement = sqlite_insert(SyncStreamRecordModel).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[
                    SyncStreamRecordModel.company_id,
                    SyncStreamRecordModel.module_id,
                    SyncStreamRecordModel.stream_id,
                ]
            )
        else:
            raise RuntimeError(
                f"P-7 Sync journal does not support database dialect {dialect!r}"
            )
        # On PostgreSQL, a concurrent INSERT ON CONFLICT waits for the winner's
        # transaction. The subsequent SELECT FOR UPDATE then observes and locks
        # the committed stream row, giving a race-safe first materialization.
        session.execute(statement)

    @staticmethod
    def _to_batch(row: SyncBatchRecordModel) -> SyncBatch:
        recorded_at = row.recorded_at
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            # SQLAlchemy's SQLite adapter round-trips timezone-aware DateTime as
            # a naive wall-clock value. SyncPublisher persists UTC, so the only
            # valid rehydration for that supported fallback dialect is UTC.
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        return SyncBatch(
            batch_id=row.batch_id,
            company_id=row.company_id,
            module_id=row.module_id,
            stream_id=row.stream_id,
            position=int(row.position),
            sync_protocol_version=row.sync_protocol_version,
            source_command_id=row.source_command_id,
            recorded_at=recorded_at,
            changes=changes_from_document(row.changes_json),
        )
