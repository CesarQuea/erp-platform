from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("client_occurred_at must be timezone-aware")


def _require_expected_version(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("expected_version must be a positive integer")


@dataclass(frozen=True, slots=True)
class CreateMilkingSession:
    command_id: UUID
    farm_id: UUID
    milking_date: date
    shift_code: str
    operator_id: UUID | None
    client_occurred_at: datetime
    client_instance_id: str | None = None

    def __post_init__(self) -> None:
        if not self.shift_code.strip():
            raise ValueError("shift_code cannot be blank")
        _require_aware(self.client_occurred_at)


@dataclass(frozen=True, slots=True)
class SetMilkingGeneral:
    command_id: UUID
    session_id: UUID
    expected_version: int
    general_gross_quantity: Decimal
    animals_milked_count: int | None
    client_occurred_at: datetime
    client_instance_id: str | None = None

    def __post_init__(self) -> None:
        _require_expected_version(self.expected_version)
        _require_aware(self.client_occurred_at)


@dataclass(frozen=True, slots=True)
class SetMilkingUseDiscard:
    command_id: UUID
    session_id: UUID
    expected_version: int
    used_on_farm_quantity: Decimal
    discarded_quantity: Decimal
    client_occurred_at: datetime
    client_instance_id: str | None = None

    def __post_init__(self) -> None:
        _require_expected_version(self.expected_version)
        _require_aware(self.client_occurred_at)


@dataclass(frozen=True, slots=True)
class SetMilkingNotes:
    command_id: UUID
    session_id: UUID
    expected_version: int
    notes: str | None
    client_occurred_at: datetime
    client_instance_id: str | None = None

    def __post_init__(self) -> None:
        _require_expected_version(self.expected_version)
        _require_aware(self.client_occurred_at)


@dataclass(frozen=True, slots=True)
class ConfirmMilkingSession:
    command_id: UUID
    session_id: UUID
    expected_version: int
    client_occurred_at: datetime
    client_instance_id: str | None = None

    def __post_init__(self) -> None:
        _require_expected_version(self.expected_version)
        _require_aware(self.client_occurred_at)


@dataclass(frozen=True, slots=True)
class CancelDraftMilkingSession:
    command_id: UUID
    session_id: UUID
    expected_version: int
    reason: str
    client_occurred_at: datetime
    client_instance_id: str | None = None

    def __post_init__(self) -> None:
        _require_expected_version(self.expected_version)
        _require_aware(self.client_occurred_at)


@dataclass(frozen=True, slots=True)
class RequestMilkingAnnulment:
    command_id: UUID
    session_id: UUID
    expected_version: int
    reason: str
    client_occurred_at: datetime
    client_instance_id: str | None = None

    def __post_init__(self) -> None:
        _require_expected_version(self.expected_version)
        _require_aware(self.client_occurred_at)
