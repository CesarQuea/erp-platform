from __future__ import annotations

from collections.abc import Iterable, Mapping
from uuid import UUID

from app.platform.identity.errors import access_denied
from app.platform.identity.model import AuthenticatedPrincipal, Role, RoleAssignment, RoleScope


def effective_permissions(
    *,
    user_id: UUID,
    tenant_id: UUID | None,
    company_id: UUID | None,
    assignments: Iterable[RoleAssignment],
    roles: Mapping[UUID, Role],
    role_permissions: Mapping[UUID, frozenset[str]],
) -> frozenset[str]:
    granted: set[str] = set()
    for assignment in assignments:
        if assignment.user_id != user_id:
            continue
        role = roles.get(assignment.role_id)
        if role is None or role.scope is not assignment.scope:
            continue
        if assignment.scope is RoleScope.PLATFORM:
            applies = True
        elif assignment.scope is RoleScope.TENANT:
            applies = tenant_id is not None and assignment.tenant_id == tenant_id
        else:
            applies = (
                tenant_id is not None
                and company_id is not None
                and assignment.tenant_id == tenant_id
                and assignment.company_id == company_id
            )
        if applies:
            granted.update(role_permissions.get(role.id, frozenset()))
    return frozenset(granted)


class AuthorizationService:
    def require(self, principal: AuthenticatedPrincipal, permission_code: str) -> None:
        if permission_code not in principal.effective_permissions:
            raise access_denied()
