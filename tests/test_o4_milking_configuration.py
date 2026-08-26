from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile
from app.modules.milking.domain import MilkingDomainError


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def test_output_profile_requires_positive_profile_and_row_versions() -> None:
    with pytest.raises(MilkingDomainError, match="OUTPUT_PROFILE_VERSION_INVALID"):
        MilkingOutputProfile(
            profile_id=uuid4(),
            profile_version=0,
            company_id=uuid4(),
            product_id=uuid4(),
            quantity_uom_id=uuid4(),
            is_active=True,
            row_version=1,
            created_at=NOW,
            created_by=uuid4(),
        )


def test_output_profile_activation_is_optimistically_versioned() -> None:
    profile = MilkingOutputProfile(
        profile_id=uuid4(),
        profile_version=1,
        company_id=uuid4(),
        product_id=uuid4(),
        quantity_uom_id=uuid4(),
        is_active=True,
        row_version=1,
        created_at=NOW,
        created_by=uuid4(),
    )
    changed = profile.with_active(active=False, expected_row_version=1)
    assert changed.is_active is False
    assert changed.row_version == 2
    with pytest.raises(MilkingDomainError, match="VERSION_CONFLICT"):
        profile.with_active(active=False, expected_row_version=2)


def test_configuration_normalizes_shift_and_versions_mutations() -> None:
    configuration = MilkingConfiguration(
        id=uuid4(),
        company_id=uuid4(),
        farm_id=uuid4(),
        shift_code=" MORNING ",
        output_profile_id=uuid4(),
        output_profile_version=1,
        is_active=True,
        version=1,
        created_at=NOW,
        created_by=uuid4(),
    )
    assert configuration.shift_code == "MORNING"
    changed = configuration.update(
        output_profile_id=None,
        output_profile_version=2,
        is_active=False,
        expected_version=1,
        actor_user_id=uuid4(),
        occurred_at=NOW,
    )
    assert changed.output_profile_version == 2
    assert changed.is_active is False
    assert changed.version == 2


def test_configuration_rejects_blank_shift() -> None:
    with pytest.raises(MilkingDomainError, match="SHIFT_REQUIRED"):
        MilkingConfiguration(
            id=uuid4(),
            company_id=uuid4(),
            farm_id=uuid4(),
            shift_code="   ",
            output_profile_id=uuid4(),
            output_profile_version=1,
            is_active=True,
            version=1,
            created_at=NOW,
            created_by=uuid4(),
        )
