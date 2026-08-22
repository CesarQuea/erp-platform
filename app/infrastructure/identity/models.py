from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


class PlatformIdentityBase(DeclarativeBase):
    pass


class UserAccountRow(PlatformIdentityBase):
    __tablename__ = "user_accounts"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    login: Mapped[str] = mapped_column(String(254), nullable=False)
    login_normalized: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(254), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasswordCredentialRow(PlatformIdentityBase):
    __tablename__ = "password_credentials"
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthSessionRow(PlatformIdentityBase):
    __tablename__ = "auth_sessions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_label: Mapped[str | None] = mapped_column(String(120))


class RefreshTokenRow(PlatformIdentityBase):
    __tablename__ = "refresh_tokens"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantMembershipRow(PlatformIdentityBase):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompanyAccessRow(PlatformIdentityBase):
    __tablename__ = "membership_company_access"
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant_memberships.id", ondelete="CASCADE"), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoleRow(PlatformIdentityBase):
    __tablename__ = "roles"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)


class PermissionRow(PlatformIdentityBase):
    __tablename__ = "permissions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(400))


class RolePermissionRow(PlatformIdentityBase):
    __tablename__ = "role_permissions"
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class RoleAssignmentRow(PlatformIdentityBase):
    __tablename__ = "principal_role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "scope_key", name="uq_role_assignment_scope"),
        CheckConstraint(
            "(scope = 'PLATFORM' AND tenant_id IS NULL AND company_id IS NULL) OR "
            "(scope = 'TENANT' AND tenant_id IS NOT NULL AND company_id IS NULL) OR "
            "(scope = 'COMPANY' AND tenant_id IS NOT NULL AND company_id IS NOT NULL)",
            name="ck_role_assignment_scope",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(160), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    company_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
