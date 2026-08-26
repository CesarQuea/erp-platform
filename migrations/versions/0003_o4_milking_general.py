"""O-4 Milking GENERAL functional schema.

Revision ID: 0003_o4_milking_general
Revises: 0002_p4_command_execution
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_o4_milking_general"
down_revision = "0002_p4_command_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic creates alembic_version.version_num as VARCHAR(32) by default.
    # O-4 intentionally keeps descriptive revision identifiers, including the
    # 35-character 0004_o4_milking_lifecycle_hardening revision. Expand the
    # internal version column before Alembic attempts to persist that revision.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )

    op.create_table(
        "milking_output_profiles",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("profile_version", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_uom_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("row_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.CheckConstraint("profile_version > 0", name="ck_milking_profile_version_positive"),
        sa.CheckConstraint("row_version > 0", name="ck_milking_profile_row_version_positive"),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_milking_profile_company", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("profile_id", "profile_version"),
        sa.UniqueConstraint(
            "company_id", "profile_id", "profile_version",
            name="uq_milking_profile_company_identity",
        ),
    )
    op.create_index(
        "ix_milking_profile_company_active",
        "milking_output_profiles",
        ["company_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "milking_configurations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("farm_id", sa.Uuid(), nullable=False),
        sa.Column("shift_code", sa.String(length=64), nullable=False),
        sa.Column("output_profile_id", sa.Uuid(), nullable=False),
        sa.Column("output_profile_version", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "char_length(btrim(shift_code)) > 0",
            name="ck_milking_configuration_shift_required",
        ),
        sa.CheckConstraint(
            "output_profile_version > 0",
            name="ck_milking_configuration_profile_version_positive",
        ),
        sa.CheckConstraint("version > 0", name="ck_milking_configuration_version_positive"),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_milking_configuration_company", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "output_profile_id", "output_profile_version"],
            [
                "milking_output_profiles.company_id",
                "milking_output_profiles.profile_id",
                "milking_output_profiles.profile_version",
            ],
            name="fk_milking_configuration_profile_same_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "farm_id", "shift_code",
            name="uq_milking_configuration_company_farm_shift",
        ),
    )
    op.create_index(
        "ix_milking_configuration_company_active",
        "milking_configurations",
        ["company_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_milking_configuration_farm",
        "milking_configurations",
        ["farm_id"],
        unique=False,
    )

    op.create_table(
        "milking_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("farm_id", sa.Uuid(), nullable=False),
        sa.Column("milking_date", sa.Date(), nullable=False),
        sa.Column("shift_code", sa.String(length=64), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("animals_milked_count", sa.Integer(), nullable=True),
        sa.Column("general_gross_quantity", sa.Numeric(), nullable=True),
        sa.Column("quantity_uom_id", sa.Uuid(), nullable=False),
        sa.Column("authoritative_gross_quantity", sa.Numeric(), nullable=True),
        sa.Column("authoritative_total_source", sa.String(length=32), nullable=True),
        sa.Column("used_on_farm_quantity", sa.Numeric(), nullable=True),
        sa.Column("discarded_quantity", sa.Numeric(), nullable=True),
        sa.Column("net_output_quantity", sa.Numeric(), nullable=True),
        sa.Column("reconciliation_status", sa.String(length=32), nullable=False),
        sa.Column("output_profile_id", sa.Uuid(), nullable=False),
        sa.Column("output_profile_version", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('DRAFT', 'DONE', 'CANCELLED')", name="ck_milking_session_status"),
        sa.CheckConstraint(
            "char_length(btrim(shift_code)) > 0",
            name="ck_milking_session_shift_required",
        ),
        sa.CheckConstraint(
            "output_profile_version > 0",
            name="ck_milking_session_profile_version_positive",
        ),
        sa.CheckConstraint("version > 0", name="ck_milking_session_version_positive"),
        sa.CheckConstraint(
            "animals_milked_count IS NULL OR animals_milked_count >= 0",
            name="ck_milking_session_animals_non_negative",
        ),
        sa.CheckConstraint(
            "general_gross_quantity IS NULL OR general_gross_quantity > 0",
            name="ck_milking_session_general_positive",
        ),
        sa.CheckConstraint(
            "used_on_farm_quantity IS NULL OR used_on_farm_quantity >= 0",
            name="ck_milking_session_used_non_negative",
        ),
        sa.CheckConstraint(
            "discarded_quantity IS NULL OR discarded_quantity >= 0",
            name="ck_milking_session_discarded_non_negative",
        ),
        sa.CheckConstraint(
            "general_gross_quantity IS NULL OR used_on_farm_quantity IS NULL OR discarded_quantity IS NULL "
            "OR used_on_farm_quantity + discarded_quantity <= general_gross_quantity",
            name="ck_milking_session_use_discard_within_general",
        ),
        sa.CheckConstraint(
            "authoritative_total_source IS NULL OR authoritative_total_source = 'GENERAL'",
            name="ck_milking_session_general_only",
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ('NOT_REQUIRED', 'MATCHED', 'MISMATCH', 'RESOLVED_WITH_DIFFERENCE')",
            name="ck_milking_session_reconciliation_status",
        ),
        sa.CheckConstraint(
            "status <> 'DONE' OR (authoritative_gross_quantity IS NOT NULL AND "
            "authoritative_total_source = 'GENERAL' AND used_on_farm_quantity IS NOT NULL AND "
            "discarded_quantity IS NOT NULL AND net_output_quantity IS NOT NULL AND "
            "confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL AND "
            "net_output_quantity = authoritative_gross_quantity - used_on_farm_quantity - discarded_quantity)",
            name="ck_milking_session_done_consistent",
        ),
        sa.CheckConstraint(
            "status <> 'CANCELLED' OR (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND char_length(btrim(cancel_reason)) > 0)",
            name="ck_milking_session_cancelled_consistent",
        ),
        sa.CheckConstraint(
            "status <> 'DRAFT' OR (authoritative_gross_quantity IS NULL AND authoritative_total_source IS NULL "
            "AND net_output_quantity IS NULL AND confirmed_at IS NULL AND confirmed_by IS NULL)",
            name="ck_milking_session_draft_not_authoritative",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_milking_session_company", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "output_profile_id", "output_profile_version"],
            [
                "milking_output_profiles.company_id",
                "milking_output_profiles.profile_id",
                "milking_output_profiles.profile_version",
            ],
            name="fk_milking_session_profile_same_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_milking_session_company_id"),
    )
    op.create_index(
        "ix_milking_session_company_date",
        "milking_sessions",
        ["company_id", "milking_date"],
        unique=False,
    )
    op.create_index(
        "ix_milking_session_company_status",
        "milking_sessions",
        ["company_id", "status"],
        unique=False,
    )
    op.create_index("ix_milking_session_farm", "milking_sessions", ["farm_id"], unique=False)
    op.create_index(
        "uq_milking_session_active_identity",
        "milking_sessions",
        ["company_id", "farm_id", "milking_date", "shift_code"],
        unique=True,
        postgresql_where=sa.text("status <> 'CANCELLED'"),
    )

    op.create_table(
        "milking_outputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("milking_session_id", sa.Uuid(), nullable=False),
        sa.Column("farm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("production_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_milking_output_quantity_positive"),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_milking_output_company", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "milking_session_id"],
            ["milking_sessions.company_id", "milking_sessions.id"],
            name="fk_milking_output_session_same_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("milking_session_id", name="uq_milking_output_session"),
    )
    op.create_index(
        "ix_milking_output_company_date",
        "milking_outputs",
        ["company_id", "production_date"],
        unique=False,
    )
    op.create_index("ix_milking_output_farm", "milking_outputs", ["farm_id"], unique=False)

    op.create_table(
        "milking_annulment_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("milking_session_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("client_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(reason)) > 0",
            name="ck_milking_annulment_reason_required",
        ),
        sa.CheckConstraint(
            "char_length(btrim(state)) > 0",
            name="ck_milking_annulment_state_required",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_milking_annulment_company", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "milking_session_id"],
            ["milking_sessions.company_id", "milking_sessions.id"],
            name="fk_milking_annulment_session_same_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_milking_annulment_pending_session",
        "milking_annulment_requests",
        ["milking_session_id"],
        unique=True,
        postgresql_where=sa.text("state = 'PENDING'"),
    )
    op.create_index(
        "ix_milking_annulment_company_state",
        "milking_annulment_requests",
        ["company_id", "state"],
        unique=False,
    )

    op.create_table(
        "milking_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("version_before", sa.BigInteger(), nullable=True),
        sa.Column("version_after", sa.BigInteger(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("client_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(event_type)) > 0",
            name="ck_milking_audit_event_type_required",
        ),
        sa.CheckConstraint(
            "version_before IS NULL OR version_before > 0",
            name="ck_milking_audit_version_before_positive",
        ),
        sa.CheckConstraint(
            "version_after IS NULL OR version_after > 0",
            name="ck_milking_audit_version_after_positive",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_milking_audit_company", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            ["milking_sessions.company_id", "milking_sessions.id"],
            name="fk_milking_audit_session_same_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_milking_audit_session_recorded",
        "milking_audit_events",
        ["session_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_milking_audit_company_recorded",
        "milking_audit_events",
        ["company_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_milking_audit_command",
        "milking_audit_events",
        ["command_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_milking_audit_command", table_name="milking_audit_events")
    op.drop_index("ix_milking_audit_company_recorded", table_name="milking_audit_events")
    op.drop_index("ix_milking_audit_session_recorded", table_name="milking_audit_events")
    op.drop_table("milking_audit_events")

    op.drop_index("ix_milking_annulment_company_state", table_name="milking_annulment_requests")
    op.drop_index("uq_milking_annulment_pending_session", table_name="milking_annulment_requests")
    op.drop_table("milking_annulment_requests")

    op.drop_index("ix_milking_output_farm", table_name="milking_outputs")
    op.drop_index("ix_milking_output_company_date", table_name="milking_outputs")
    op.drop_table("milking_outputs")

    op.drop_index("uq_milking_session_active_identity", table_name="milking_sessions")
    op.drop_index("ix_milking_session_farm", table_name="milking_sessions")
    op.drop_index("ix_milking_session_company_status", table_name="milking_sessions")
    op.drop_index("ix_milking_session_company_date", table_name="milking_sessions")
    op.drop_table("milking_sessions")

    op.drop_index("ix_milking_configuration_farm", table_name="milking_configurations")
    op.drop_index("ix_milking_configuration_company_active", table_name="milking_configurations")
    op.drop_table("milking_configurations")

    op.drop_index("ix_milking_profile_company_active", table_name="milking_output_profiles")
    op.drop_table("milking_output_profiles")

    # Downgrading 0003 leaves a <=32-character revision (0002), so restore the
    # Alembic default width after all O-4 objects have been removed.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=128),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
