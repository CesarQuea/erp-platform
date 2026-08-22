from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Company:
    id: UUID
    code: str
    legal_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        code = self.code.strip()
        legal_name = self.legal_name.strip()
        if not code:
            raise ValueError("Company code must not be blank")
        if len(code) > 64:
            raise ValueError("Company code must not exceed 64 characters")
        if not legal_name:
            raise ValueError("Company legal_name must not be blank")
        if len(legal_name) > 255:
            raise ValueError("Company legal_name must not exceed 255 characters")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Company timestamps must be timezone-aware")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "legal_name", legal_name)
