"""Add P-7 Sync Foundation journal persistence.

Revision ID: 0006_p7_sync_foundation
Revises: 0005_p5_module_activation
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_p7_sync_foundation"
down_revision = "0005_p5_module_activation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_sync_streams",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.String(length=64), nullable=False),
        sa.Column("stream_id", sa.String(length=64), nullable=False),
        sa.Column("current_position", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "current_position >= 0",
            name="ck_sync_stream_position_nonnegative",
        ),
        sa.CheckConstraint(
            "length(trim(module_id)) > 0",
            name="ck_sync_stream_module_id_required",
        ),
        sa.CheckConstraint(
            "length(trim(stream_id)) > 0",
            name="ck_sync_stream_stream_id_required",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_sync_stream_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("company_id", "module_id", "stream_id"),
    )

    op.create_table(
        "platform_sync_batches",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.String(length=64), nullable=False),
        sa.Column("stream_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("sync_protocol_version", sa.String(length=32), nullable=False),
        sa.Column("source_command_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changes_json", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "position >= 1",
            name="ck_sync_batch_position_positive",
        ),
        sa.CheckConstraint(
            "length(trim(sync_protocol_version)) > 0",
            name="ck_sync_batch_protocol_required",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "module_id", "stream_id"],
            [
                "platform_sync_streams.company_id",
                "platform_sync_streams.module_id",
                "platform_sync_streams.stream_id",
            ],
            name="fk_sync_batch_stream",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("batch_id"),
        sa.UniqueConstraint(
            "company_id",
            "module_id",
            "stream_id",
            "position",
            name="uq_sync_batch_stream_position",
        ),
    )


def downgrade() -> None:
    op.drop_table("platform_sync_batches")
    op.drop_table("platform_sync_streams")
