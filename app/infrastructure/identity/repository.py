from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update

from app.infrastructure.identity.models import AuthSessionRow, CompanyAccessRow, PasswordCredentialRow, PermissionRow, RefreshTokenRow, RoleAssignmentRow, RolePermissionRow, RoleRow, TenantMembershipRow, UserAccountRow
from app.infrastructure.identity.session_scope import PlatformSessionScope
from app.platform.identity.model import AccessStatus, AuthSession, CompanyAccess, Permission, RefreshTokenRecord, Role, RoleAssignment, RoleScope, TenantMembership, UserAccount, UserStatus


def _scope_key(assignment: RoleAssignment) -> str:
    if assignment.scope is RoleScope.PLATFORM:
        return "platform"
    if assignment.scope is RoleScope.TENANT:
        return f"tenant:{assignment.tenant_id}"
    return f"company:{assignment.tenant_id}:{assignment.company_id}"


class SqlAlchemyIdentityRepository:
    def __init__(self, scope: PlatformSessionScope) -> None:
        self._scope = scope

    def _session(self):
        return self._scope.current()

    def add_user(self, user: UserAccount) -> None:
        self._session().add(UserAccountRow(id=user.id, login=user.login, login_normalized=user.login_normalized, display_name=user.display_name, email=user.email, status=user.status.value, created_at=user.created_at, updated_at=user.updated_at))

    def get_user_by_id(self, user_id: UUID) -> UserAccount | None:
        row = self._session().get(UserAccountRow, user_id)
        return self._user(row) if row else None

    def get_user_by_normalized_login(self, login_normalized: str) -> UserAccount | None:
        row = self._session().execute(select(UserAccountRow).where(UserAccountRow.login_normalized == login_normalized)).scalar_one_or_none()
        return self._user(row) if row else None

    def set_password_hash(self, user_id: UUID, password_hash: str, updated_at: datetime) -> None:
        row = self._session().get(PasswordCredentialRow, user_id)
        if row is None:
            self._session().add(PasswordCredentialRow(user_id=user_id, password_hash=password_hash, updated_at=updated_at))
        else:
            row.password_hash = password_hash
            row.updated_at = updated_at

    def get_password_hash(self, user_id: UUID) -> str | None:
        row = self._session().get(PasswordCredentialRow, user_id)
        return row.password_hash if row else None

    def add_session(self, session: AuthSession) -> None:
        self._session().add(AuthSessionRow(id=session.id, user_id=session.user_id, created_at=session.created_at, last_seen_at=session.last_seen_at, expires_at=session.expires_at, revoked_at=session.revoked_at, client_label=session.client_label))

    def get_session(self, session_id: UUID) -> AuthSession | None:
        row = self._session().get(AuthSessionRow, session_id)
        return self._auth_session(row) if row else None

    def touch_session(self, session_id: UUID, at: datetime) -> None:
        self._session().execute(update(AuthSessionRow).where(AuthSessionRow.id == session_id).values(last_seen_at=at))

    def revoke_session(self, session_id: UUID, at: datetime) -> None:
        self._session().execute(update(AuthSessionRow).where(AuthSessionRow.id == session_id, AuthSessionRow.revoked_at.is_(None)).values(revoked_at=at))

    def revoke_all_sessions(self, user_id: UUID, at: datetime) -> None:
        self._session().execute(update(AuthSessionRow).where(AuthSessionRow.user_id == user_id, AuthSessionRow.revoked_at.is_(None)).values(revoked_at=at))

    def add_refresh_token(self, token: RefreshTokenRecord) -> None:
        self._session().add(RefreshTokenRow(id=token.id, session_id=token.session_id, family_id=token.family_id, token_hash=token.token_hash, created_at=token.created_at, expires_at=token.expires_at, consumed_at=token.consumed_at, revoked_at=token.revoked_at))

    def get_refresh_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        row = self._session().execute(select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)).scalar_one_or_none()
        return self._refresh(row) if row else None

    def consume_refresh(self, token_id: UUID, at: datetime) -> bool:
        result = self._session().execute(update(RefreshTokenRow).where(RefreshTokenRow.id == token_id, RefreshTokenRow.consumed_at.is_(None), RefreshTokenRow.revoked_at.is_(None)).values(consumed_at=at).returning(RefreshTokenRow.id)).scalar_one_or_none()
        return result is not None

    def revoke_refresh_family(self, family_id: UUID, at: datetime) -> None:
        self._session().execute(update(RefreshTokenRow).where(RefreshTokenRow.family_id == family_id, RefreshTokenRow.revoked_at.is_(None)).values(revoked_at=at))

    def revoke_refresh_for_session(self, session_id: UUID, at: datetime) -> None:
        self._session().execute(update(RefreshTokenRow).where(RefreshTokenRow.session_id == session_id, RefreshTokenRow.revoked_at.is_(None)).values(revoked_at=at))

    def add_membership(self, membership: TenantMembership) -> None:
        self._session().add(TenantMembershipRow(id=membership.id, user_id=membership.user_id, tenant_id=membership.tenant_id, status=membership.status.value, created_at=membership.created_at, updated_at=membership.updated_at))

    def get_membership(self, user_id: UUID, tenant_id: UUID) -> TenantMembership | None:
        row = self._session().execute(select(TenantMembershipRow).where(TenantMembershipRow.user_id == user_id, TenantMembershipRow.tenant_id == tenant_id)).scalar_one_or_none()
        return self._membership(row) if row else None

    def list_memberships(self, user_id: UUID) -> Sequence[TenantMembership]:
        rows = self._session().execute(select(TenantMembershipRow).where(TenantMembershipRow.user_id == user_id)).scalars().all()
        return [self._membership(row) for row in rows]

    def add_company_access(self, access: CompanyAccess) -> None:
        self._session().add(CompanyAccessRow(membership_id=access.membership_id, company_id=access.company_id, status=access.status.value, created_at=access.created_at, updated_at=access.updated_at))

    def get_company_access(self, membership_id: UUID, company_id: UUID) -> CompanyAccess | None:
        row = self._session().get(CompanyAccessRow, (membership_id, company_id))
        return self._company_access(row) if row else None

    def list_company_access(self, membership_id: UUID) -> Sequence[CompanyAccess]:
        rows = self._session().execute(select(CompanyAccessRow).where(CompanyAccessRow.membership_id == membership_id)).scalars().all()
        return [self._company_access(row) for row in rows]

    def add_permission(self, permission: Permission) -> None:
        self._session().add(PermissionRow(id=permission.id, code=permission.code, description=permission.description))

    def get_permission_by_code(self, code: str) -> Permission | None:
        row = self._session().execute(select(PermissionRow).where(PermissionRow.code == code)).scalar_one_or_none()
        return Permission(row.id, row.code, row.description) if row else None

    def add_role(self, role: Role) -> None:
        self._session().add(RoleRow(id=role.id, code=role.code, scope=role.scope.value, name=role.name))

    def get_role_by_code(self, code: str) -> Role | None:
        row = self._session().execute(select(RoleRow).where(RoleRow.code == code)).scalar_one_or_none()
        return self._role(row) if row else None

    def grant_permission_to_role(self, role_id: UUID, permission_id: UUID) -> None:
        existing = self._session().get(RolePermissionRow, (role_id, permission_id))
        if existing is None:
            self._session().add(RolePermissionRow(role_id=role_id, permission_id=permission_id))

    def add_role_assignment(self, assignment: RoleAssignment) -> None:
        self._session().add(RoleAssignmentRow(id=assignment.id, user_id=assignment.user_id, role_id=assignment.role_id, scope=assignment.scope.value, scope_key=_scope_key(assignment), tenant_id=assignment.tenant_id, company_id=assignment.company_id))

    def list_role_assignments(self, user_id: UUID) -> Sequence[RoleAssignment]:
        rows = self._session().execute(select(RoleAssignmentRow).where(RoleAssignmentRow.user_id == user_id)).scalars().all()
        return [RoleAssignment(id=row.id, user_id=row.user_id, role_id=row.role_id, scope=RoleScope(row.scope), tenant_id=row.tenant_id, company_id=row.company_id) for row in rows]

    def get_roles(self, role_ids: Sequence[UUID]) -> Sequence[Role]:
        if not role_ids:
            return []
        rows = self._session().execute(select(RoleRow).where(RoleRow.id.in_(role_ids))).scalars().all()
        return [self._role(row) for row in rows]

    def get_permission_codes_by_roles(self, role_ids: Sequence[UUID]) -> dict[UUID, frozenset[str]]:
        if not role_ids:
            return {}
        rows = self._session().execute(select(RolePermissionRow.role_id, PermissionRow.code).join(PermissionRow, PermissionRow.id == RolePermissionRow.permission_id).where(RolePermissionRow.role_id.in_(role_ids))).all()
        result: dict[UUID, set[str]] = {role_id: set() for role_id in role_ids}
        for role_id, code in rows:
            result.setdefault(role_id, set()).add(code)
        return {role_id: frozenset(codes) for role_id, codes in result.items()}

    @staticmethod
    def _user(row: UserAccountRow) -> UserAccount:
        return UserAccount(row.id, row.login, row.login_normalized, row.display_name, row.email, UserStatus(row.status), row.created_at, row.updated_at)

    @staticmethod
    def _auth_session(row: AuthSessionRow) -> AuthSession:
        return AuthSession(row.id, row.user_id, row.created_at, row.expires_at, row.last_seen_at, row.revoked_at, row.client_label)

    @staticmethod
    def _refresh(row: RefreshTokenRow) -> RefreshTokenRecord:
        return RefreshTokenRecord(row.id, row.session_id, row.family_id, row.token_hash, row.created_at, row.expires_at, row.consumed_at, row.revoked_at)

    @staticmethod
    def _membership(row: TenantMembershipRow) -> TenantMembership:
        return TenantMembership(row.id, row.user_id, row.tenant_id, AccessStatus(row.status), row.created_at, row.updated_at)

    @staticmethod
    def _company_access(row: CompanyAccessRow) -> CompanyAccess:
        return CompanyAccess(row.membership_id, row.company_id, AccessStatus(row.status), row.created_at, row.updated_at)

    @staticmethod
    def _role(row: RoleRow) -> Role:
        return Role(row.id, row.code, RoleScope(row.scope), row.name)
