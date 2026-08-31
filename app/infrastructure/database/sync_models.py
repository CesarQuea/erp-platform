from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models import Base


class SyncStreamRecordModel(Base):
    __tablename__ = "platform_sync_streams"
    __table_args__ = (
        CheckConstraint(
            "current_position >= 0",
            name="ck_sync_stream_position_nonnegative",
        ),
        CheckConstraint(
            "length(trim(module_id)) > 0",
            name="ck_sync_stream_module_id_required",
        ),
        CheckConstraint(
            "length(trim(stream_id)) > 0",
            name="ck_sync_stream_stream_id_required",
        ),
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_sync_stream_company",
            ondelete="RESTRICT",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stream_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    current_position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SyncBatchRecordModel(Base):
    __tablename__ = "platform_sync_batches"
    __table_args__ = (
        CheckConstraint("position >= 1", name="ck_sync_batch_position_positive"),
        CheckConstraint(
            "length(trim(sync_protocol_version)) > 0",
            name="ck_sync_batch_protocol_required",
        ),
        ForeignKeyConstraint(
            ["company_id", "module_id", "stream_id"],
            [
                "platform_sync_streams.company_id",
                "platform_sync_streams.module_id",
                "platform_sync_streams.stream_id",
            ],
            name="fk_sync_batch_stream",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "module_id",
            "stream_id",
            "position",
            name="uq_sync_batch_stream_position",
        ),
    )

    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    module_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stream_id: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sync_protocol_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_command_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changes_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
