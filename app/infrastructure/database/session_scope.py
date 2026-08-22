from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from uuid import UUID

from sqlalchemy.orm import Session

from app.platform.tenancy.errors import TenantSessionScopeError


@dataclass(frozen=True, slots=True)
class ActiveTenantSession:
    tenant_id: UUID
    session: Session


_active_tenant_session: ContextVar[ActiveTenantSession | None] = ContextVar(
    "active_tenant_session",
    default=None,
)


class TenantSessionScope:
    @contextmanager
    def activate(self, tenant_id: UUID, session: Session) -> Iterator[None]:
        existing = _active_tenant_session.get()
        if existing is not None:
            raise TenantSessionScopeError("Nested tenant transaction scopes are not supported")
        token = _active_tenant_session.set(ActiveTenantSession(tenant_id, session))
        try:
            yield
        finally:
            _active_tenant_session.reset(token)

    def current(self, *, expected_tenant_id: UUID | None = None) -> Session:
        active = _active_tenant_session.get()
        if active is None:
            raise TenantSessionScopeError("No active tenant transaction scope")
        if expected_tenant_id is not None and active.tenant_id != expected_tenant_id:
            raise TenantSessionScopeError("Active session belongs to a different tenant")
        return active.session
