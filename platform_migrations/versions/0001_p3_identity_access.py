"""P-3 global identity and access authority.

Revision ID: 0001_p3_identity_access
Revises:
Create Date: 2026-08-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_p3_identity_access"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    ts = sa.DateTime(timezone=True)
    op.create_table("user_accounts", sa.Column("id", uuid, primary_key=True), sa.Column("login", sa.String(254), nullable=False), sa.Column("login_normalized", sa.String(254), nullable=False), sa.Column("display_name", sa.String(254), nullable=False), sa.Column("email", sa.String(320), nullable=True), sa.Column("status", sa.String(16), nullable=False), sa.Column("created_at", ts, nullable=False), sa.Column("updated_at", ts, nullable=False), sa.UniqueConstraint("login_normalized", name="uq_user_login_normalized"))
    op.create_table("password_credentials", sa.Column("user_id", uuid, sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), primary_key=True), sa.Column("password_hash", sa.Text(), nullable=False), sa.Column("updated_at", ts, nullable=False))
    op.create_table("auth_sessions", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid, sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("created_at", ts, nullable=False), sa.Column("last_seen_at", ts, nullable=False), sa.Column("expires_at", ts, nullable=False), sa.Column("revoked_at", ts, nullable=True), sa.Column("client_label", sa.String(120), nullable=True))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table("refresh_tokens", sa.Column("id", uuid, primary_key=True), sa.Column("session_id", uuid, sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("family_id", uuid, nullable=False), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("created_at", ts, nullable=False), sa.Column("expires_at", ts, nullable=False), sa.Column("consumed_at", ts, nullable=True), sa.Column("revoked_at", ts, nullable=True), sa.UniqueConstraint("token_hash", name="uq_refresh_token_hash"))
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_table("tenant_memberships", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid, sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("tenant_id", uuid, nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("created_at", ts, nullable=False), sa.Column("updated_at", ts, nullable=False), sa.UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"))
    op.create_table("membership_company_access", sa.Column("membership_id", uuid, sa.ForeignKey("tenant_memberships.id", ondelete="CASCADE"), primary_key=True), sa.Column("company_id", uuid, primary_key=True), sa.Column("status", sa.String(16), nullable=False), sa.Column("created_at", ts, nullable=False), sa.Column("updated_at", ts, nullable=False))
    op.create_table("roles", sa.Column("id", uuid, primary_key=True), sa.Column("code", sa.String(120), nullable=False), sa.Column("scope", sa.String(16), nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.UniqueConstraint("code", name="uq_role_code"))
    op.create_table("permissions", sa.Column("id", uuid, primary_key=True), sa.Column("code", sa.String(160), nullable=False), sa.Column("description", sa.String(400), nullable=True), sa.UniqueConstraint("code", name="uq_permission_code"))
    op.create_table("role_permissions", sa.Column("role_id", uuid, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True), sa.Column("permission_id", uuid, sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("principal_role_assignments", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid, sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("role_id", uuid, sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False), sa.Column("scope", sa.String(16), nullable=False), sa.Column("scope_key", sa.String(160), nullable=False), sa.Column("tenant_id", uuid, nullable=True), sa.Column("company_id", uuid, nullable=True), sa.UniqueConstraint("user_id", "role_id", "scope_key", name="uq_role_assignment_scope"), sa.CheckConstraint("(scope = 'PLATFORM' AND tenant_id IS NULL AND company_id IS NULL) OR (scope = 'TENANT' AND tenant_id IS NOT NULL AND company_id IS NULL) OR (scope = 'COMPANY' AND tenant_id IS NOT NULL AND company_id IS NOT NULL)", name="ck_role_assignment_scope"))


def downgrade() -> None:
    op.drop_table("principal_role_assignments")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("membership_company_access")
    op.drop_table("tenant_memberships")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("password_credentials")
    op.drop_table("user_accounts")
