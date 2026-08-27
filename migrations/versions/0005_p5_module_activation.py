"""Add P-5 Company-scoped module activation foundation.

Revision ID: 0005_p5_module_activation
Revises: 0004_o4_milking_lifecycle_hardening
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_p5_module_activation"
down_revision = "0004_o4_milking_lifecycle_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_module_activations",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "state IN ('ENABLED', 'DISABLED')",
            name="ck_module_activation_state",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_module_activation_version_positive",
        ),
        sa.CheckConstraint(
            "length(trim(module_id)) > 0",
            name="ck_module_activation_module_id_required",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_module_activation_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("company_id", "module_id"),
    )
    op.create_index(
        "ix_module_activation_company_state",
        "platform_module_activations",
        ["company_id", "state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_module_activation_company_state",
        table_name="platform_module_activations",
    )
    op.drop_table("platform_module_activations")
