from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.milking.domain import (
    MilkingDomainError,
    MilkingSession,
    MilkingSessionStatus,
    MilkingTotalSource,
)


def _draft() -> MilkingSession:
    return MilkingSession.new_draft(
        company_id=uuid4(),
        farm_id=uuid4(),
        milking_date=date(2026, 8, 25),
        shift_code="MORNING",
        operator_id=None,
        quantity_uom_id=uuid4(),
        output_profile_id=uuid4(),
        output_profile_version=1,
        product_id=uuid4(),
        actor_user_id=uuid4(),
        occurred_at=datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc),
    )


def test_new_draft_starts_without_authoritative_total() -> None:
    session = _draft()

    assert session.status is MilkingSessionStatus.DRAFT
    assert session.version == 1
    assert session.authoritative_gross_quantity is None
    assert session.authoritative_total_source is None
    assert session.net_output_quantity is None


def test_general_and_use_discard_preserve_decimal_exactness() -> None:
    actor = uuid4()
    session = _draft().set_general(
        gross_quantity=Decimal("102.50"),
        animals_milked_count=75,
        expected_version=1,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )
    session = session.set_use_discard(
        used_on_farm_quantity=Decimal("8.00"),
        discarded_quantity=Decimal("1.50"),
        expected_version=2,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )

    confirmed, output = session.confirm(
        expected_version=3,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )

    assert confirmed.status is MilkingSessionStatus.DONE
    assert confirmed.authoritative_total_source is MilkingTotalSource.GENERAL
    assert confirmed.net_output_quantity == Decimal("93.00")
    assert output is not None
    assert output.quantity == Decimal("93.00")
    assert output.farm_id == confirmed.farm_id
    assert output.product_id == confirmed.product_id
    assert output.uom_id == confirmed.quantity_uom_id


def test_zero_net_confirms_without_output() -> None:
    actor = uuid4()
    session = _draft().set_general(
        gross_quantity=Decimal("10"),
        animals_milked_count=None,
        expected_version=1,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )
    session = session.set_use_discard(
        used_on_farm_quantity=Decimal("8"),
        discarded_quantity=Decimal("2"),
        expected_version=2,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )

    confirmed, output = session.confirm(
        expected_version=3,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )

    assert confirmed.net_output_quantity == Decimal("0")
    assert output is None


def test_use_discard_cannot_exceed_general() -> None:
    actor = uuid4()
    session = _draft().set_general(
        gross_quantity=Decimal("10"),
        animals_milked_count=5,
        expected_version=1,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )

    with pytest.raises(MilkingDomainError, match="USE_DISCARD_EXCEEDS_GENERAL"):
        session.set_use_discard(
            used_on_farm_quantity=Decimal("9"),
            discarded_quantity=Decimal("2"),
            expected_version=2,
            actor_user_id=actor,
            occurred_at=datetime.now(timezone.utc),
        )


def test_confirm_requires_explicit_use_and_discard() -> None:
    actor = uuid4()
    session = _draft().set_general(
        gross_quantity=Decimal("10"),
        animals_milked_count=None,
        expected_version=1,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )

    with pytest.raises(MilkingDomainError, match="USED_ON_FARM_REQUIRED"):
        session.confirm(
            expected_version=2,
            actor_user_id=actor,
            occurred_at=datetime.now(timezone.utc),
        )


def test_cancel_draft_releases_business_state_and_requires_reason() -> None:
    actor = uuid4()
    session = _draft()

    with pytest.raises(MilkingDomainError, match="CANCEL_REASON_REQUIRED"):
        session.cancel_draft(
            reason="  ",
            expected_version=1,
            actor_user_id=actor,
            occurred_at=datetime.now(timezone.utc),
        )

    cancelled = session.cancel_draft(
        reason="registro equivocado",
        expected_version=1,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )
    assert cancelled.status is MilkingSessionStatus.CANCELLED
    assert cancelled.cancel_reason == "registro equivocado"


def test_stale_expected_version_fails_closed() -> None:
    session = _draft()

    with pytest.raises(MilkingDomainError, match="VERSION_CONFLICT"):
        session.set_notes(
            notes="nota",
            expected_version=99,
            actor_user_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
        )


def test_notes_are_trimmed_blank_to_null_and_capped() -> None:
    actor = uuid4()
    session = _draft().set_notes(
        notes="  texto  ",
        expected_version=1,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )
    assert session.notes == "texto"

    session = session.set_notes(
        notes="   ",
        expected_version=2,
        actor_user_id=actor,
        occurred_at=datetime.now(timezone.utc),
    )
    assert session.notes is None

    with pytest.raises(MilkingDomainError, match="NOTES_TOO_LONG"):
        session.set_notes(
            notes="x" * 501,
            expected_version=3,
            actor_user_id=actor,
            occurred_at=datetime.now(timezone.utc),
        )
