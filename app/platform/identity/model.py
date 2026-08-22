from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


class AccessStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class RoleScope(StrEnum):
    PLATFORM = "PLATFORM"
    TENANT = "TENANT"
    COMPANY = "COMPANY"


@dataclass(frozen=True, slots=True)
class UserAccount:
    id: UUID
    login: str
    login_normalized: str
    display_name: str
    email: str | None
    status: UserStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AuthSession:
    id: UUID
    user_id: UUID
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None = None
    client_label: str | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


@dataclass(frozen=True, slots=True)
class TenantMembership:
    id: UUID
    user_id: UUID
    tenant_id: UUID
    status: AccessStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CompanyAccess:
    membership_id: UUID
    company_id: UUID
    status: AccessStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Permission:
    id: UUID
    code: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class Role:
    id: UUID
    code: str
    scope: RoleScope
    name: str


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    id: UUID
    user_id: UUID
    role_id: UUID
    scope: RoleScope
    tenant_id: UUID | None = None
    company_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.scope is RoleScope.PLATFORM:
            if self.tenant_id is not None or self.company_id is not None:
                raise ValueError("PLATFORM role assignment cannot include tenant/company scope")
        elif self.scope is RoleScope.TENANT:
            if self.tenant_id is None or self.company_id is not None:
                raise ValueError("TENANT role assignment requires tenant_id and no company_id")
        elif self.scope is RoleScope.COMPANY:
            if self.tenant_id is None or self.company_id is None:
                raise ValueError("COMPANY role assignment requires tenant_id and company_id")


@dataclass(frozen=True, slots=True)
class CompanyContext:
    tenant_id: UUID
    company_id: UUID


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: UUID
    session_id: UUID
    tenant_id: UUID | None = None
    company_id: UUID | None = None
    effective_permissions: frozenset[str] = field(default_factory=frozenset)

    @property
    def has_operational_context(self) -> bool:
        return self.tenant_id is not None and self.company_id is not None


@dataclass(frozen=True, slots=True)
class RefreshTokenRecord:
    id: UUID
    session_id: UUID
    family_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None
