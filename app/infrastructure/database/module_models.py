from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models import Base


class ModuleActivationRecord(Base):
    __tablename__ = "platform_module_activations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('ENABLED', 'DISABLED')",
            name="ck_module_activation_state",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_module_activation_version_positive",
        ),
        CheckConstraint(
            "char_length(trim(module_id)) > 0",
            name="ck_module_activation_module_id_required",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
