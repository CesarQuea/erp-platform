from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantConnectionConfig:
    tenant_id: UUID
    database_url: str = field(repr=False)
    is_active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active must be a boolean")
        database_url = self.database_url.strip()
        if not database_url:
            raise ValueError("database_url must not be blank")
        object.__setattr__(self, "database_url", database_url)


class TenantRegistry(Protocol):
    def get(self, tenant_id: UUID) -> TenantConnectionConfig:
        """Return technical connection metadata for one configured tenant."""
