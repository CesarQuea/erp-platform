from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.core.identifiers.uuid import new_uuid
from app.core.time.clock import Clock, SystemClock
from app.core.transactions.boundary import TransactionBoundary
from app.platform.company.model import Company
from app.platform.identity.authorization import effective_permissions
from app.platform.identity.errors import (
    access_denied,
    authentication_failed,
    identity_conflict,
    identity_not_found,
)
from app.platform.identity.model import (
    AccessStatus,
    AuthenticatedPrincipal,
    AuthSession,
    CompanyAccess,
    Permission,
    RefreshTokenRecord,
    Role,
    RoleAssignment,
    RoleScope,
    TenantMembership,
    UserAccount,
    UserStatus,
)
from app.platform.identity.policy import PasswordPolicy, normalize_login
from app.platform.identity.repository import IdentityRepository
from app.platform.identity.security import (
    AccessTokenClaims,
    AccessTokenCodec,
    PasswordHasher,
    RefreshTokenGenerator,
)
from app.platform.tenancy.registry import TenantRegistry

logger = logging.getLogger(__name__)


class CompanyDirectory(Protocol):
    def get_company(self, tenant_id: UUID, company_id: UUID) -> Company | None: ...


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    session_id: UUID
    access_expires_at: datetime
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class ContextToken:
    access_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthorizedContext:
    tenant_id: UUID
    company_id: UUID
    company_code: str
    company_name: str


class AuthenticationService:
    def __init__(
        self,
        repository: IdentityRepository,
        transaction: TransactionBoundary,
        password_hasher: PasswordHasher,
        token_codec: AccessTokenCodec,
        refresh_tokens: RefreshTokenGenerator,
        company_directory: CompanyDirectory,
        *,
        issuer: str,
        audience: str,
        clock: Clock | None = None,
        id_factory=None,
        access_token_ttl: timedelta = timedelta(minutes=15),
        refresh_token_ttl: timedelta = timedelta(days=30),
    ) -> None:
        self._repository = repository
        self._transaction = transaction
        self._password_hasher = password_hasher
        self._token_codec = token_codec
        self._refresh_tokens = refresh_tokens
        self._company_directory = company_directory
        self._issuer = issuer
        self._audience = audience
        self._clock = clock or SystemClock()
        self._id_factory = id_factory or new_uuid
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl
        self._dummy_password_hash = self._password_hasher.hash(
            "dummy-password-not-a-real-account"
        )

    def login(
        self,
        *,
        login: str,
        password: str,
        client_label: str | None = None,
    ) -> TokenPair:
        now = self._clock.now()
        normalized = normalize_login(login)

        def operation():
            user = self._repository.get_user_by_normalized_login(normalized)
            if user is None:
                self._password_hasher.verify(password, self._dummy_password_hash)
                return None
            password_hash = self._repository.get_password_hash(user.id)
            if (
                user.status is not UserStatus.ACTIVE
                or password_hash is None
                or not self._password_hasher.verify(password, password_hash)
            ):
                return None
            session = AuthSession(
                id=self._id_factory(),
                user_id=user.id,
                created_at=now,
                expires_at=now + self._refresh_token_ttl,
                last_seen_at=now,
                client_label=client_label,
            )
            refresh = self._refresh_tokens.generate()
            refresh_expires_at = now + self._refresh_token_ttl
            self._repository.add_session(session)
            self._repository.add_refresh_token(
                RefreshTokenRecord(
                    id=self._id_factory(),
                    session_id=session.id,
                    family_id=self._id_factory(),
                    token_hash=refresh.token_hash,
                    created_at=now,
                    expires_at=refresh_expires_at,
                )
            )
            return user, session, refresh.plaintext, refresh_expires_at

        result = self._transaction.run(operation)
        if result is None:
            logger.info("login_failed")
            raise authentication_failed()
        user, session, refresh_plaintext, refresh_expires_at = result
        logger.info(
            "login_succeeded",
            extra={"user_id": str(user.id), "session_id": str(session.id)},
        )
        access, access_expires_at = self._issue_access_token(user.id, session.id)
        return TokenPair(
            access,
            refresh_plaintext,
            session.id,
            access_expires_at,
            refresh_expires_at,
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        now = self._clock.now()
        token_hash = self._refresh_tokens.hash_token(refresh_token)

        def operation():
            record = self._repository.get_refresh_by_hash(token_hash)
            if record is None:
                return None
            session = self._repository.get_session(record.session_id)
            if (
                record.revoked_at is not None
                or record.consumed_at is not None
                or record.expires_at <= now
            ):
                self._repository.revoke_refresh_family(record.family_id, now)
                self._repository.revoke_session(record.session_id, now)
                return None
            if session is None or session.revoked_at is not None or session.expires_at <= now:
                self._repository.revoke_refresh_family(record.family_id, now)
                if session is not None:
                    self._repository.revoke_session(session.id, now)
                return None
            user = self._repository.get_user_by_id(session.user_id)
            if user is None or user.status is not UserStatus.ACTIVE:
                self._repository.revoke_refresh_family(record.family_id, now)
                self._repository.revoke_session(session.id, now)
                return None
            if not self._repository.consume_refresh(record.id, now):
                self._repository.revoke_refresh_family(record.family_id, now)
                self._repository.revoke_session(session.id, now)
                return None
            material = self._refresh_tokens.generate()
            expires_at = now + self._refresh_token_ttl
            self._repository.add_refresh_token(
                RefreshTokenRecord(
                    id=self._id_factory(),
                    session_id=session.id,
                    family_id=record.family_id,
                    token_hash=material.token_hash,
                    created_at=now,
                    expires_at=expires_at,
                )
            )
            self._repository.touch_session(session.id, now)
            return user, session, material.plaintext, expires_at

        result = self._transaction.run(operation)
        if result is None:
            logger.warning("refresh_rejected")
            raise authentication_failed()
        user, session, new_refresh, refresh_expires_at = result
        access, access_expires_at = self._issue_access_token(user.id, session.id)
        logger.info(
            "refresh_succeeded",
            extra={"user_id": str(user.id), "session_id": str(session.id)},
        )
        return TokenPair(
            access,
            new_refresh,
            session.id,
            access_expires_at,
            refresh_expires_at,
        )

    def principal_from_access_token(self, token: str) -> AuthenticatedPrincipal:
        try:
            claims = self._token_codec.decode(token)
        except ValueError:
            raise authentication_failed() from None
        now = self._clock.now()

        def operation() -> AuthenticatedPrincipal | None:
            session = self._repository.get_session(claims.session_id)
            if (
                session is None
                or session.user_id != claims.user_id
                or session.revoked_at is not None
                or session.expires_at <= now
            ):
                return None
            user = self._repository.get_user_by_id(claims.user_id)
            if user is None or user.status is not UserStatus.ACTIVE:
                return None
            if (claims.tenant_id is None) != (claims.company_id is None):
                return None
            if claims.tenant_id is not None and claims.company_id is not None:
                membership = self._repository.get_membership(user.id, claims.tenant_id)
                if membership is None or membership.status is not AccessStatus.ACTIVE:
                    return None
                company_access = self._repository.get_company_access(
                    membership.id,
                    claims.company_id,
                )
                if company_access is None or company_access.status is not AccessStatus.ACTIVE:
                    return None
            assignments = self._repository.list_role_assignments(user.id)
            role_ids = [assignment.role_id for assignment in assignments]
            roles = {role.id: role for role in self._repository.get_roles(role_ids)}
            permissions = self._repository.get_permission_codes_by_roles(role_ids)
            principal = AuthenticatedPrincipal(
                user_id=user.id,
                session_id=session.id,
                tenant_id=claims.tenant_id,
                company_id=claims.company_id,
                effective_permissions=effective_permissions(
                    user_id=user.id,
                    tenant_id=claims.tenant_id,
                    company_id=claims.company_id,
                    assignments=assignments,
                    roles=roles,
                    role_permissions=permissions,
                ),
            )
            self._repository.touch_session(session.id, now)
            return principal

        principal = self._transaction.run(operation)
        if principal is None:
            raise authentication_failed()
        if principal.tenant_id is not None and principal.company_id is not None:
            company = self._company_directory.get_company(
                principal.tenant_id,
                principal.company_id,
            )
            if company is None or not company.is_active:
                raise access_denied()
        return principal

    def logout(self, access_token: str) -> None:
        try:
            claims = self._token_codec.decode(access_token)
        except ValueError:
            raise authentication_failed() from None
        now = self._clock.now()

        def operation() -> None:
            session = self._repository.get_session(claims.session_id)
            if session is None or session.user_id != claims.user_id:
                return
            self._repository.revoke_session(session.id, now)
            self._repository.revoke_refresh_for_session(session.id, now)

        self._transaction.run(operation)
        logger.info("logout", extra={"session_id": str(claims.session_id)})

    def get_user(self, principal: AuthenticatedPrincipal) -> UserAccount:
        user = self._transaction.run(
            lambda: self._repository.get_user_by_id(principal.user_id)
        )
        if user is None or user.status is not UserStatus.ACTIVE:
            raise authentication_failed()
        return user

    def list_contexts(self, principal: AuthenticatedPrincipal) -> list[AuthorizedContext]:
        def operation():
            rows: list[tuple[UUID, UUID]] = []
            for membership in self._repository.list_memberships(principal.user_id):
                if membership.status is not AccessStatus.ACTIVE:
                    continue
                for access in self._repository.list_company_access(membership.id):
                    if access.status is AccessStatus.ACTIVE:
                        rows.append((membership.tenant_id, access.company_id))
            return rows

        candidates = self._transaction.run(operation)
        contexts: list[AuthorizedContext] = []
        for tenant_id, company_id in candidates:
            company = self._company_directory.get_company(tenant_id, company_id)
            if company is not None and company.is_active:
                contexts.append(
                    AuthorizedContext(
                        tenant_id=tenant_id,
                        company_id=company_id,
                        company_code=company.code,
                        company_name=company.legal_name,
                    )
                )
        return contexts

    def select_context(
        self,
        principal: AuthenticatedPrincipal,
        *,
        tenant_id: UUID,
        company_id: UUID,
    ) -> ContextToken:
        company = self._company_directory.get_company(tenant_id, company_id)
        if company is None or not company.is_active:
            raise access_denied()
        now = self._clock.now()

        def operation() -> bool:
            session = self._repository.get_session(principal.session_id)
            user = self._repository.get_user_by_id(principal.user_id)
            if (
                session is None
                or session.user_id != principal.user_id
                or session.revoked_at is not None
                or session.expires_at <= now
                or user is None
                or user.status is not UserStatus.ACTIVE
            ):
                return False
            membership = self._repository.get_membership(principal.user_id, tenant_id)
            if membership is None or membership.status is not AccessStatus.ACTIVE:
                return False
            access = self._repository.get_company_access(membership.id, company_id)
            if access is None or access.status is not AccessStatus.ACTIVE:
                return False
            return True

        if not self._transaction.run(operation):
            raise access_denied()
        token, expires_at = self._issue_access_token(
            principal.user_id,
            principal.session_id,
            tenant_id=tenant_id,
            company_id=company_id,
        )
        return ContextToken(token, expires_at)

    def _issue_access_token(
        self,
        user_id: UUID,
        session_id: UUID,
        *,
        tenant_id: UUID | None = None,
        company_id: UUID | None = None,
    ) -> tuple[str, datetime]:
        now = self._clock.now()
        expires_at = now + self._access_token_ttl
        claims = AccessTokenClaims(
            issuer=self._issuer,
            audience=self._audience,
            user_id=user_id,
            session_id=session_id,
            token_id=self._id_factory(),
            issued_at=now,
            expires_at=expires_at,
            tenant_id=tenant_id,
            company_id=company_id,
        )
        return self._token_codec.encode(claims), expires_at


class IdentityProvisioningService:
    def __init__(
        self,
        repository: IdentityRepository,
        transaction: TransactionBoundary,
        password_hasher: PasswordHasher,
        tenant_registry: TenantRegistry,
        company_directory: CompanyDirectory,
        *,
        password_policy: PasswordPolicy | None = None,
        clock: Clock | None = None,
        id_factory=None,
    ) -> None:
        self._repository = repository
        self._transaction = transaction
        self._password_hasher = password_hasher
        self._tenant_registry = tenant_registry
        self._company_directory = company_directory
        self._password_policy = password_policy or PasswordPolicy()
        self._clock = clock or SystemClock()
        self._id_factory = id_factory or new_uuid

    def create_user(
        self,
        *,
        login: str,
        password: str,
        display_name: str,
        email: str | None = None,
    ) -> UserAccount:
        normalized = normalize_login(login)
        self._password_policy.validate(password=password, login=login)
        now = self._clock.now()
        user = UserAccount(
            id=self._id_factory(),
            login=login.strip(),
            login_normalized=normalized,
            display_name=display_name.strip(),
            email=email.strip() if email else None,
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        if not user.display_name:
            raise ValueError("display_name cannot be blank")
        password_hash = self._password_hasher.hash(password)

        def operation() -> UserAccount:
            if self._repository.get_user_by_normalized_login(normalized) is not None:
                raise identity_conflict("Login is already in use.")
            self._repository.add_user(user)
            self._repository.set_password_hash(user.id, password_hash, now)
            return user

        return self._transaction.run(operation)

    def change_password(self, user_id: UUID, *, new_password: str) -> None:
        now = self._clock.now()

        def operation() -> None:
            user = self._repository.get_user_by_id(user_id)
            if user is None:
                raise identity_not_found()
            self._password_policy.validate(password=new_password, login=user.login)
            self._repository.set_password_hash(
                user_id,
                self._password_hasher.hash(new_password),
                now,
            )
            self._repository.revoke_all_sessions(user_id, now)
            self._repository.revoke_refresh_for_user(user_id, now)

        self._transaction.run(operation)

    def set_user_status(self, user_id: UUID, status: UserStatus) -> None:
        now = self._clock.now()

        def operation() -> None:
            user = self._repository.get_user_by_id(user_id)
            if user is None:
                raise identity_not_found()
            self._repository.set_user_status(user_id, status, now)
            if status is not UserStatus.ACTIVE:
                self._repository.revoke_all_sessions(user_id, now)
                self._repository.revoke_refresh_for_user(user_id, now)

        self._transaction.run(operation)

    def grant_membership(self, user_id: UUID, tenant_id: UUID) -> TenantMembership:
        config = self._tenant_registry.get(tenant_id)
        if not config.is_active:
            raise access_denied()
        now = self._clock.now()

        def operation() -> TenantMembership:
            if self._repository.get_user_by_id(user_id) is None:
                raise identity_not_found()
            existing = self._repository.get_membership(user_id, tenant_id)
            if existing is not None:
                if existing.status is not AccessStatus.ACTIVE:
                    self._repository.set_membership_status(
                        existing.id,
                        AccessStatus.ACTIVE,
                        now,
                    )
                    return TenantMembership(
                        existing.id,
                        existing.user_id,
                        existing.tenant_id,
                        AccessStatus.ACTIVE,
                        existing.created_at,
                        now,
                    )
                return existing
            membership = TenantMembership(
                self._id_factory(),
                user_id,
                tenant_id,
                AccessStatus.ACTIVE,
                now,
                now,
            )
            self._repository.add_membership(membership)
            return membership

        return self._transaction.run(operation)

    def revoke_membership(self, user_id: UUID, tenant_id: UUID) -> None:
        now = self._clock.now()

        def operation() -> None:
            membership = self._repository.get_membership(user_id, tenant_id)
            if membership is not None and membership.status is not AccessStatus.REVOKED:
                self._repository.set_membership_status(
                    membership.id,
                    AccessStatus.REVOKED,
                    now,
                )

        self._transaction.run(operation)

    def grant_company_access(
        self,
        user_id: UUID,
        tenant_id: UUID,
        company_id: UUID,
    ) -> CompanyAccess:
        company = self._company_directory.get_company(tenant_id, company_id)
        if company is None or not company.is_active:
            raise access_denied()
        now = self._clock.now()

        def operation() -> CompanyAccess:
            membership = self._repository.get_membership(user_id, tenant_id)
            if membership is None or membership.status is not AccessStatus.ACTIVE:
                raise access_denied()
            existing = self._repository.get_company_access(membership.id, company_id)
            if existing is not None:
                if existing.status is not AccessStatus.ACTIVE:
                    self._repository.set_company_access_status(
                        membership.id,
                        company_id,
                        AccessStatus.ACTIVE,
                        now,
                    )
                    return CompanyAccess(
                        membership.id,
                        company_id,
                        AccessStatus.ACTIVE,
                        existing.created_at,
                        now,
                    )
                return existing
            access = CompanyAccess(
                membership.id,
                company_id,
                AccessStatus.ACTIVE,
                now,
                now,
            )
            self._repository.add_company_access(access)
            return access

        return self._transaction.run(operation)

    def revoke_company_access(
        self,
        user_id: UUID,
        tenant_id: UUID,
        company_id: UUID,
    ) -> None:
        now = self._clock.now()

        def operation() -> None:
            membership = self._repository.get_membership(user_id, tenant_id)
            if membership is None:
                return
            access = self._repository.get_company_access(membership.id, company_id)
            if access is not None and access.status is not AccessStatus.REVOKED:
                self._repository.set_company_access_status(
                    membership.id,
                    company_id,
                    AccessStatus.REVOKED,
                    now,
                )

        self._transaction.run(operation)

    def ensure_permission(
        self,
        code: str,
        *,
        description: str | None = None,
    ) -> Permission:
        def operation() -> Permission:
            existing = self._repository.get_permission_by_code(code)
            if existing is not None:
                return existing
            permission = Permission(self._id_factory(), code, description)
            self._repository.add_permission(permission)
            return permission

        return self._transaction.run(operation)

    def ensure_role(self, code: str, *, name: str, scope: RoleScope) -> Role:
        def operation() -> Role:
            existing = self._repository.get_role_by_code(code)
            if existing is not None:
                if existing.scope is not scope:
                    raise identity_conflict(
                        "Role code already exists with another scope."
                    )
                return existing
            role = Role(self._id_factory(), code, scope, name)
            self._repository.add_role(role)
            return role

        return self._transaction.run(operation)

    def grant_permission_to_role(self, role_id: UUID, permission_id: UUID) -> None:
        self._transaction.run(
            lambda: self._repository.grant_permission_to_role(role_id, permission_id)
        )

    def assign_role(
        self,
        user_id: UUID,
        role_id: UUID,
        *,
        tenant_id: UUID | None = None,
        company_id: UUID | None = None,
    ) -> RoleAssignment:
        def operation() -> RoleAssignment:
            if self._repository.get_user_by_id(user_id) is None:
                raise identity_not_found()
            roles = self._repository.get_roles([role_id])
            if not roles:
                raise identity_not_found("Role was not found.")
            role = roles[0]
            if role.scope is RoleScope.TENANT:
                membership = (
                    self._repository.get_membership(user_id, tenant_id)
                    if tenant_id
                    else None
                )
                if membership is None or membership.status is not AccessStatus.ACTIVE:
                    raise access_denied()
            elif role.scope is RoleScope.COMPANY:
                membership = (
                    self._repository.get_membership(user_id, tenant_id)
                    if tenant_id
                    else None
                )
                access = (
                    self._repository.get_company_access(membership.id, company_id)
                    if membership and company_id
                    else None
                )
                if (
                    membership is None
                    or membership.status is not AccessStatus.ACTIVE
                    or access is None
                    or access.status is not AccessStatus.ACTIVE
                ):
                    raise access_denied()
            candidate = RoleAssignment(
                id=self._id_factory(),
                user_id=user_id,
                role_id=role_id,
                scope=role.scope,
                tenant_id=tenant_id,
                company_id=company_id,
            )
            for existing in self._repository.list_role_assignments(user_id):
                if (
                    existing.role_id == candidate.role_id
                    and existing.scope is candidate.scope
                    and existing.tenant_id == candidate.tenant_id
                    and existing.company_id == candidate.company_id
                ):
                    return existing
            self._repository.add_role_assignment(candidate)
            return candidate

        return self._transaction.run(operation)

    def revoke_role_assignment(self, assignment_id: UUID) -> None:
        self._transaction.run(
            lambda: self._repository.delete_role_assignment(assignment_id)
        )
