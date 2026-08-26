from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models import Base


class MilkingOutputProfileRecord(Base):
    __tablename__ = "milking_output_profiles"
    __table_args__ = (
        CheckConstraint("profile_version > 0", name="ck_milking_profile_version_positive"),
        CheckConstraint("row_version > 0", name="ck_milking_profile_row_version_positive"),
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_milking_profile_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "profile_id",
            "profile_version",
            name="uq_milking_profile_company_identity",
        ),
        Index("ix_milking_profile_company_active", "company_id", "is_active"),
    )

    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    profile_version: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity_uom_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class MilkingConfigurationRecord(Base):
    __tablename__ = "milking_configurations"
    __table_args__ = (
        CheckConstraint("char_length(btrim(shift_code)) > 0", name="ck_milking_configuration_shift_required"),
        CheckConstraint("output_profile_version > 0", name="ck_milking_configuration_profile_version_positive"),
        CheckConstraint("version > 0", name="ck_milking_configuration_version_positive"),
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_milking_configuration_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "output_profile_id", "output_profile_version"],
            [
                "milking_output_profiles.company_id",
                "milking_output_profiles.profile_id",
                "milking_output_profiles.profile_version",
            ],
            name="fk_milking_configuration_profile_same_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "farm_id",
            "shift_code",
            name="uq_milking_configuration_company_farm_shift",
        ),
        Index("ix_milking_configuration_company_active", "company_id", "is_active"),
        Index("ix_milking_configuration_farm", "farm_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    farm_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    shift_code: Mapped[str] = mapped_column(String(64), nullable=False)
    output_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    output_profile_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class MilkingSessionRecord(Base):
    __tablename__ = "milking_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'DONE', 'CANCELLED')", name="ck_milking_session_status"),
        CheckConstraint("char_length(btrim(shift_code)) > 0", name="ck_milking_session_shift_required"),
        CheckConstraint("output_profile_version > 0", name="ck_milking_session_profile_version_positive"),
        CheckConstraint("version > 0", name="ck_milking_session_version_positive"),
        CheckConstraint(
            "animals_milked_count IS NULL OR animals_milked_count >= 0",
            name="ck_milking_session_animals_non_negative",
        ),
        CheckConstraint(
            "general_gross_quantity IS NULL OR general_gross_quantity > 0",
            name="ck_milking_session_general_positive",
        ),
        CheckConstraint(
            "used_on_farm_quantity IS NULL OR used_on_farm_quantity >= 0",
            name="ck_milking_session_used_non_negative",
        ),
        CheckConstraint(
            "discarded_quantity IS NULL OR discarded_quantity >= 0",
            name="ck_milking_session_discarded_non_negative",
        ),
        CheckConstraint(
            "general_gross_quantity IS NULL OR used_on_farm_quantity IS NULL OR discarded_quantity IS NULL "
            "OR used_on_farm_quantity + discarded_quantity <= general_gross_quantity",
            name="ck_milking_session_use_discard_within_general",
        ),
        CheckConstraint(
            "authoritative_total_source IS NULL OR authoritative_total_source = 'GENERAL'",
            name="ck_milking_session_general_only",
        ),
        CheckConstraint(
            "reconciliation_status IN ('NOT_REQUIRED', 'MATCHED', 'MISMATCH', 'RESOLVED_WITH_DIFFERENCE')",
            name="ck_milking_session_reconciliation_status",
        ),
        CheckConstraint(
            "status <> 'DONE' OR ("
            "authoritative_gross_quantity IS NOT NULL AND "
            "authoritative_total_source = 'GENERAL' AND "
            "used_on_farm_quantity IS NOT NULL AND "
            "discarded_quantity IS NOT NULL AND "
            "net_output_quantity IS NOT NULL AND "
            "confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL AND "
            "net_output_quantity = authoritative_gross_quantity - used_on_farm_quantity - discarded_quantity"
            ")",
            name="ck_milking_session_done_consistent",
        ),
        CheckConstraint(
            "status <> 'CANCELLED' OR (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND char_length(btrim(cancel_reason)) > 0)",
            name="ck_milking_session_cancelled_consistent",
        ),
        CheckConstraint(
            "status <> 'DRAFT' OR (authoritative_gross_quantity IS NULL AND authoritative_total_source IS NULL "
            "AND net_output_quantity IS NULL AND confirmed_at IS NULL AND confirmed_by IS NULL)",
            name="ck_milking_session_draft_not_authoritative",
        ),
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_milking_session_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "output_profile_id", "output_profile_version"],
            [
                "milking_output_profiles.company_id",
                "milking_output_profiles.profile_id",
                "milking_output_profiles.profile_version",
            ],
            name="fk_milking_session_profile_same_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_milking_session_company_id"),
        Index("ix_milking_session_company_date", "company_id", "milking_date"),
        Index("ix_milking_session_company_status", "company_id", "status"),
        Index("ix_milking_session_farm", "farm_id"),
        Index(
            "uq_milking_session_active_identity",
            "company_id",
            "farm_id",
            "milking_date",
            "shift_code",
            unique=True,
            postgresql_where=text("status <> 'CANCELLED'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    farm_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    milking_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_code: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    animals_milked_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    general_gross_quantity: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    quantity_uom_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authoritative_gross_quantity: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    authoritative_total_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    used_on_farm_quantity: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    discarded_quantity: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    net_output_quantity: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    reconciliation_status: Mapped[str] = mapped_column(String(32), nullable=False)

    output_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    output_profile_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class MilkingOutputRecord(Base):
    __tablename__ = "milking_outputs"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_milking_output_quantity_positive"),
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_milking_output_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "milking_session_id"],
            ["milking_sessions.company_id", "milking_sessions.id"],
            name="fk_milking_output_session_same_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("milking_session_id", name="uq_milking_output_session"),
        Index("ix_milking_output_company_date", "company_id", "production_date"),
        Index("ix_milking_output_farm", "farm_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    milking_session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    farm_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    uom_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    production_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class MilkingAnnulmentRequestRecord(Base):
    __tablename__ = "milking_annulment_requests"
    __table_args__ = (
        CheckConstraint("char_length(btrim(reason)) > 0", name="ck_milking_annulment_reason_required"),
        CheckConstraint("char_length(btrim(state)) > 0", name="ck_milking_annulment_state_required"),
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_milking_annulment_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "milking_session_id"],
            ["milking_sessions.company_id", "milking_sessions.id"],
            name="fk_milking_annulment_session_same_company",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_milking_annulment_pending_session",
            "milking_session_id",
            unique=True,
            postgresql_where=text("state = 'PENDING'"),
        ),
        Index("ix_milking_annulment_company_state", "company_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    milking_session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)


class MilkingAuditEventRecord(Base):
    __tablename__ = "milking_audit_events"
    __table_args__ = (
        CheckConstraint("char_length(btrim(event_type)) > 0", name="ck_milking_audit_event_type_required"),
        CheckConstraint(
            "version_before IS NULL OR version_before > 0",
            name="ck_milking_audit_version_before_positive",
        ),
        CheckConstraint(
            "version_after IS NULL OR version_after > 0",
            name="ck_milking_audit_version_after_positive",
        ),
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_milking_audit_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["milking_sessions.company_id", "milking_sessions.id"],
            name="fk_milking_audit_session_same_company",
            ondelete="RESTRICT",
        ),
        Index("ix_milking_audit_session_recorded", "session_id", "recorded_at"),
        Index("ix_milking_audit_company_recorded", "company_id", "recorded_at"),
        Index("ix_milking_audit_command", "command_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    command_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version_before: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    version_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
