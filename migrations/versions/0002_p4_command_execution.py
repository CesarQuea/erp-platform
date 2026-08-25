"""P-4 command idempotency foundation

Revision ID: 0002_p4_command_execution
Revises: 0001_p2_tenant_company
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_p4_command_execution"
down_revision = "0001_p2_tenant_company"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_command_executions",
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("command_name", sa.String(length=128), nullable=False),
        sa.Column("command_schema_version", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("result_code", sa.String(length=128), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scope IN ('TENANT', 'COMPANY')",
            name="ck_command_execution_scope",
        ),
        sa.CheckConstraint(
            "(scope = 'TENANT' AND company_id IS NULL) OR "
            "(scope = 'COMPANY' AND company_id IS NOT NULL)",
            name="ck_command_execution_company_scope",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_command_execution_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("command_id"),
    )


def downgrade() -> None:
    op.drop_table("platform_command_executions")
