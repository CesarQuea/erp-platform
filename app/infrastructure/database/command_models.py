from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models import Base


class CommandExecutionRecordModel(Base):
    __tablename__ = "platform_command_executions"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('TENANT', 'COMPANY')",
            name="ck_command_execution_scope",
        ),
        CheckConstraint(
            "(scope = 'TENANT' AND company_id IS NULL) OR "
            "(scope = 'COMPANY' AND company_id IS NOT NULL)",
            name="ck_command_execution_company_scope",
        ),
    )

    command_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    command_name: Mapped[str] = mapped_column(String(128), nullable=False)
    command_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
