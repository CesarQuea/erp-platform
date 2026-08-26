from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.milking.admin_commands import (
    CreateMilkingConfiguration,
    SetOutputProfileActive,
    UpdateMilkingConfiguration,
)


NOW = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)


@pytest.mark.parametrize("profile_version", [0, -1, True])
def test_output_profile_activation_rejects_invalid_profile_version(profile_version) -> None:
    with pytest.raises(ValueError, match="profile_version must be a positive integer"):
        SetOutputProfileActive(
            command_id=uuid4(),
            profile_id=uuid4(),
            profile_version=profile_version,
            expected_version=1,
            is_active=True,
            client_occurred_at=NOW,
        )


def test_configuration_create_rejects_non_positive_profile_version() -> None:
    with pytest.raises(ValueError, match="profile_version must be a positive integer"):
        CreateMilkingConfiguration(
            command_id=uuid4(),
            farm_id=uuid4(),
            shift_code="MORNING",
            output_profile_id=uuid4(),
            output_profile_version=0,
            client_occurred_at=NOW,
        )


def test_configuration_update_rejects_non_positive_profile_version() -> None:
    with pytest.raises(ValueError, match="profile_version must be a positive integer"):
        UpdateMilkingConfiguration(
            command_id=uuid4(),
            configuration_id=uuid4(),
            expected_version=1,
            output_profile_id=uuid4(),
            output_profile_version=0,
            is_active=None,
            client_occurred_at=NOW,
        )
