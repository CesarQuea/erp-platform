"""Harden O-4 Milking GENERAL lifecycle constraints.

Revision ID: 0004_o4_milking_lifecycle_hardening
Revises: 0003_o4_milking_general
"""
from __future__ import annotations

from alembic import op

revision = "0004_o4_milking_lifecycle_hardening"
down_revision = "0003_o4_milking_general"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_milking_session_done_consistent",
        "milking_sessions",
        type_="check",
    )
    op.drop_constraint(
        "ck_milking_session_cancelled_consistent",
        "milking_sessions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_milking_session_done_consistent",
        "milking_sessions",
        "status <> 'DONE' OR ("
        "general_gross_quantity IS NOT NULL AND "
        "authoritative_gross_quantity IS NOT NULL AND "
        "authoritative_gross_quantity = general_gross_quantity AND "
        "authoritative_total_source = 'GENERAL' AND "
        "used_on_farm_quantity IS NOT NULL AND "
        "discarded_quantity IS NOT NULL AND "
        "net_output_quantity IS NOT NULL AND "
        "reconciliation_status = 'NOT_REQUIRED' AND "
        "confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL AND "
        "net_output_quantity = authoritative_gross_quantity - used_on_farm_quantity - discarded_quantity"
        ")",
    )
    op.create_check_constraint(
        "ck_milking_session_cancelled_consistent",
        "milking_sessions",
        "status <> 'CANCELLED' OR ("
        "cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL AND "
        "cancel_reason IS NOT NULL AND char_length(btrim(cancel_reason)) > 0"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_milking_session_done_consistent",
        "milking_sessions",
        type_="check",
    )
    op.drop_constraint(
        "ck_milking_session_cancelled_consistent",
        "milking_sessions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_milking_session_done_consistent",
        "milking_sessions",
        "status <> 'DONE' OR ("
        "authoritative_gross_quantity IS NOT NULL AND "
        "authoritative_total_source = 'GENERAL' AND "
        "used_on_farm_quantity IS NOT NULL AND "
        "discarded_quantity IS NOT NULL AND "
        "net_output_quantity IS NOT NULL AND "
        "confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL AND "
        "net_output_quantity = authoritative_gross_quantity - used_on_farm_quantity - discarded_quantity"
        ")",
    )
    op.create_check_constraint(
        "ck_milking_session_cancelled_consistent",
        "milking_sessions",
        "status <> 'CANCELLED' OR ("
        "cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL AND "
        "char_length(btrim(cancel_reason)) > 0"
        ")",
    )
