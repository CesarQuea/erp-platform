from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from app.modules.milking.domain import MilkingDomainError


@dataclass(frozen=True, slots=True)
class MilkingOutputProfile:
    profile_id: UUID
    profile_version: int
    company_id: UUID
    product_id: UUID
    quantity_uom_id: UUID
    is_active: bool
    row_version: int
    created_at: datetime
    created_by: UUID

    def __post_init__(self) -> None:
        if self.profile_version <= 0:
            raise MilkingDomainError("OUTPUT_PROFILE_VERSION_INVALID")
        if self.row_version <= 0:
            raise MilkingDomainError("VERSION_CONFLICT")

    def with_active(
        self,
        *,
        active: bool,
        expected_row_version: int,
    ) -> "MilkingOutputProfile":
        if self.row_version != expected_row_version:
            raise MilkingDomainError("VERSION_CONFLICT")
        return replace(self, is_active=active, row_version=self.row_version + 1)


@dataclass(frozen=True, slots=True)
class MilkingConfiguration:
    id: UUID
    company_id: UUID
    farm_id: UUID
    shift_code: str
    output_profile_id: UUID
    output_profile_version: int
    is_active: bool
    version: int
    created_at: datetime
    created_by: UUID
    updated_at: datetime | None = None
    updated_by: UUID | None = None

    def __post_init__(self) -> None:
        normalized_shift = self.shift_code.strip()
        if not normalized_shift:
            raise MilkingDomainError("SHIFT_REQUIRED")
        if normalized_shift != self.shift_code:
            object.__setattr__(self, "shift_code", normalized_shift)
        if self.output_profile_version <= 0:
            raise MilkingDomainError("OUTPUT_PROFILE_VERSION_INVALID")
        if self.version <= 0:
            raise MilkingDomainError("VERSION_CONFLICT")

    def update(
        self,
        *,
        output_profile_id: UUID | None,
        output_profile_version: int | None,
        is_active: bool | None,
        expected_version: int,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> "MilkingConfiguration":
        if self.version != expected_version:
            raise MilkingDomainError("VERSION_CONFLICT")
        next_profile_id = output_profile_id or self.output_profile_id
        next_profile_version = (
            output_profile_version
            if output_profile_version is not None
            else self.output_profile_version
        )
        if next_profile_version <= 0:
            raise MilkingDomainError("OUTPUT_PROFILE_VERSION_INVALID")
        return replace(
            self,
            output_profile_id=next_profile_id,
            output_profile_version=next_profile_version,
            is_active=self.is_active if is_active is None else is_active,
            version=self.version + 1,
            updated_at=occurred_at,
            updated_by=actor_user_id,
        )
