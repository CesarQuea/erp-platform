from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: UUID

    @classmethod
    def from_value(cls, value: UUID | str) -> "TenantContext":
        if isinstance(value, UUID):
            return cls(value)
        return cls(UUID(str(value)))
