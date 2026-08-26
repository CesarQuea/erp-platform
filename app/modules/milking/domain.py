from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class MilkingDomainError(ValueError):
    """Typed domain validation/state error raised before persistence."""


class MilkingSessionStatus(StrEnum):
    DRAFT = "DRAFT"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class MilkingTotalSource(StrEnum):
    GENERAL = "GENERAL"
    INDIVIDUAL_TOTAL = "INDIVIDUAL_TOTAL"
    GROUP_TOTAL = "GROUP_TOTAL"


class MilkingReconciliationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    RESOLVED_WITH_DIFFERENCE = "RESOLVED_WITH_DIFFERENCE"


def _require_version(current: int, expected: int) -> None:
    if current != expected:
        raise MilkingDomainError("VERSION_CONFLICT")


def _require_draft(status: MilkingSessionStatus) -> None:
    if status is not MilkingSessionStatus.DRAFT:
        raise MilkingDomainError("STATE_CONFLICT")


def normalize_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    normalized = notes.strip()
    if not normalized:
        return None
    if len(normalized) > 500:
        raise MilkingDomainError("NOTES_TOO_LONG")
    return normalized


@dataclass(frozen=True, slots=True)
class MilkingOutput:
    id: UUID
    company_id: UUID
    milking_session_id: UUID
    farm_id: UUID
    product_id: UUID
    quantity: Decimal
    uom_id: UUID
    production_date: date
    created_at: datetime
    created_by: UUID

    def __post_init__(self) -> None:
        if self.quantity <= Decimal("0"):
            raise MilkingDomainError("OUTPUT_MUST_BE_POSITIVE")


@dataclass(frozen=True, slots=True)
class MilkingSession:
    id: UUID
    company_id: UUID
    farm_id: UUID
    milking_date: date
    shift_code: str
    operator_id: UUID | None
    status: MilkingSessionStatus

    animals_milked_count: int | None
    general_gross_quantity: Decimal | None
    quantity_uom_id: UUID

    authoritative_gross_quantity: Decimal | None
    authoritative_total_source: MilkingTotalSource | None
    used_on_farm_quantity: Decimal | None
    discarded_quantity: Decimal | None
    net_output_quantity: Decimal | None
    reconciliation_status: MilkingReconciliationStatus

    output_profile_id: UUID
    output_profile_version: int
    product_id: UUID
    notes: str | None
    version: int

    created_at: datetime
    created_by: UUID
    updated_at: datetime | None
    updated_by: UUID | None
    confirmed_at: datetime | None
    confirmed_by: UUID | None
    cancelled_at: datetime | None
    cancelled_by: UUID | None
    cancel_reason: str | None

    @classmethod
    def new_draft(
        cls,
        *,
        company_id: UUID,
        farm_id: UUID,
        milking_date: date,
        shift_code: str,
        operator_id: UUID | None,
        quantity_uom_id: UUID,
        output_profile_id: UUID,
        output_profile_version: int,
        product_id: UUID,
        actor_user_id: UUID,
        occurred_at: datetime,
        session_id: UUID | None = None,
    ) -> MilkingSession:
        normalized_shift = shift_code.strip()
        if not normalized_shift:
            raise MilkingDomainError("SHIFT_REQUIRED")
        if output_profile_version <= 0:
            raise MilkingDomainError("OUTPUT_PROFILE_VERSION_INVALID")
        return cls(
            id=session_id or uuid4(),
            company_id=company_id,
            farm_id=farm_id,
            milking_date=milking_date,
            shift_code=normalized_shift,
            operator_id=operator_id,
            status=MilkingSessionStatus.DRAFT,
            animals_milked_count=None,
            general_gross_quantity=None,
            quantity_uom_id=quantity_uom_id,
            authoritative_gross_quantity=None,
            authoritative_total_source=None,
            used_on_farm_quantity=None,
            discarded_quantity=None,
            net_output_quantity=None,
            reconciliation_status=MilkingReconciliationStatus.NOT_REQUIRED,
            output_profile_id=output_profile_id,
            output_profile_version=output_profile_version,
            product_id=product_id,
            notes=None,
            version=1,
            created_at=occurred_at,
            created_by=actor_user_id,
            updated_at=None,
            updated_by=None,
            confirmed_at=None,
            confirmed_by=None,
            cancelled_at=None,
            cancelled_by=None,
            cancel_reason=None,
        )

    def set_general(
        self,
        *,
        gross_quantity: Decimal,
        animals_milked_count: int | None,
        expected_version: int,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> MilkingSession:
        _require_draft(self.status)
        _require_version(self.version, expected_version)
        if gross_quantity <= Decimal("0"):
            raise MilkingDomainError("GENERAL_GROSS_MUST_BE_POSITIVE")
        if animals_milked_count is not None and animals_milked_count < 0:
            raise MilkingDomainError("ANIMAL_COUNT_NEGATIVE")
        if (
            self.used_on_farm_quantity is not None
            and self.discarded_quantity is not None
            and self.used_on_farm_quantity + self.discarded_quantity > gross_quantity
        ):
            raise MilkingDomainError("USE_DISCARD_EXCEEDS_GENERAL")
        return replace(
            self,
            general_gross_quantity=gross_quantity,
            animals_milked_count=animals_milked_count,
            version=self.version + 1,
            updated_at=occurred_at,
            updated_by=actor_user_id,
        )

    def set_use_discard(
        self,
        *,
        used_on_farm_quantity: Decimal,
        discarded_quantity: Decimal,
        expected_version: int,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> MilkingSession:
        _require_draft(self.status)
        _require_version(self.version, expected_version)
        if used_on_farm_quantity < Decimal("0") or discarded_quantity < Decimal("0"):
            raise MilkingDomainError("USE_OR_DISCARD_NEGATIVE")
        if (
            self.general_gross_quantity is not None
            and used_on_farm_quantity + discarded_quantity > self.general_gross_quantity
        ):
            raise MilkingDomainError("USE_DISCARD_EXCEEDS_GENERAL")
        return replace(
            self,
            used_on_farm_quantity=used_on_farm_quantity,
            discarded_quantity=discarded_quantity,
            version=self.version + 1,
            updated_at=occurred_at,
            updated_by=actor_user_id,
        )

    def set_notes(
        self,
        *,
        notes: str | None,
        expected_version: int,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> MilkingSession:
        _require_draft(self.status)
        _require_version(self.version, expected_version)
        return replace(
            self,
            notes=normalize_notes(notes),
            version=self.version + 1,
            updated_at=occurred_at,
            updated_by=actor_user_id,
        )

    def confirm(
        self,
        *,
        expected_version: int,
        actor_user_id: UUID,
        occurred_at: datetime,
        output_id: UUID | None = None,
    ) -> tuple[MilkingSession, MilkingOutput | None]:
        _require_draft(self.status)
        _require_version(self.version, expected_version)
        gross = self.general_gross_quantity
        used = self.used_on_farm_quantity
        discarded = self.discarded_quantity
        if gross is None:
            raise MilkingDomainError("GENERAL_TOTAL_REQUIRED")
        if used is None:
            raise MilkingDomainError("USED_ON_FARM_REQUIRED")
        if discarded is None:
            raise MilkingDomainError("DISCARDED_REQUIRED")
        if gross <= Decimal("0"):
            raise MilkingDomainError("GENERAL_GROSS_MUST_BE_POSITIVE")
        if used < Decimal("0") or discarded < Decimal("0") or used + discarded > gross:
            raise MilkingDomainError("INVALID_USE_DISCARD")

        net = gross - used - discarded
        confirmed = replace(
            self,
            status=MilkingSessionStatus.DONE,
            authoritative_gross_quantity=gross,
            authoritative_total_source=MilkingTotalSource.GENERAL,
            net_output_quantity=net,
            reconciliation_status=MilkingReconciliationStatus.NOT_REQUIRED,
            version=self.version + 1,
            updated_at=occurred_at,
            updated_by=actor_user_id,
            confirmed_at=occurred_at,
            confirmed_by=actor_user_id,
        )
        output = None
        if net > Decimal("0"):
            output = MilkingOutput(
                id=output_id or uuid4(),
                company_id=self.company_id,
                milking_session_id=self.id,
                farm_id=self.farm_id,
                product_id=self.product_id,
                quantity=net,
                uom_id=self.quantity_uom_id,
                production_date=self.milking_date,
                created_at=occurred_at,
                created_by=actor_user_id,
            )
        return confirmed, output

    def cancel_draft(
        self,
        *,
        reason: str,
        expected_version: int,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> MilkingSession:
        _require_draft(self.status)
        _require_version(self.version, expected_version)
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise MilkingDomainError("CANCEL_REASON_REQUIRED")
        return replace(
            self,
            status=MilkingSessionStatus.CANCELLED,
            version=self.version + 1,
            updated_at=occurred_at,
            updated_by=actor_user_id,
            cancelled_at=occurred_at,
            cancelled_by=actor_user_id,
            cancel_reason=normalized_reason,
        )
