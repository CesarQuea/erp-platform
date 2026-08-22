from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")

    @classmethod
    def from_value(cls, value: UUID | str) -> "TenantContext":
        if isinstance(value, UUID):
            return cls(value)
        return cls(UUID(str(value)))
