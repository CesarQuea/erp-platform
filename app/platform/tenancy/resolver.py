from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.platform.tenancy.context import TenantContext


class TenantDataSource(Protocol):
    @property
    def tenant_id(self) -> UUID:
        ...


class TenantDataSourceResolver(Protocol):
    def resolve(self, context: TenantContext) -> TenantDataSource:
        ...

    def dispose(self) -> None:
        ...
