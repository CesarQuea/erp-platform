from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from app.modules.milking.domain import MilkingDomainError, MilkingSession, MilkingSessionStatus


def validate_annulment_request(
    session: MilkingSession,
    *,
    reason: str,
    expected_version: int,
) -> str:
    if session.status is not MilkingSessionStatus.DONE:
        raise MilkingDomainError("STATE_CONFLICT")
    if session.version != expected_version:
        raise MilkingDomainError("VERSION_CONFLICT")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise MilkingDomainError("ANNULMENT_REASON_REQUIRED")
    return normalized_reason


def annul_done_without_output(
    session: MilkingSession,
    *,
    reason: str,
    expected_version: int,
    actor_user_id: UUID,
    occurred_at: datetime,
) -> MilkingSession:
    normalized_reason = validate_annulment_request(
        session,
        reason=reason,
        expected_version=expected_version,
    )
    return replace(
        session,
        status=MilkingSessionStatus.CANCELLED,
        version=session.version + 1,
        updated_at=occurred_at,
        updated_by=actor_user_id,
        cancelled_at=occurred_at,
        cancelled_by=actor_user_id,
        cancel_reason=normalized_reason,
    )
