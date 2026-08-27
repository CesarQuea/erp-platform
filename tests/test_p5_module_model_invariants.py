from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from uuid import uuid4

import pytest

from app.platform.modules.model import (
    CompanyModuleActivation,
    CompanyModuleStatus,
    ModuleActivationState,
    ModuleDefinition,
)


_DEFINITION = ModuleDefinition("milking", "1.0.0", "milking")


def test_absent_status_must_be_disabled_version_zero() -> None:
    with pytest.raises(ValueError):
        CompanyModuleStatus(
            definition=_DEFINITION,
            state=ModuleActivationState.ENABLED,
            version=0,
            activation_present=False,
            effective_enabled=False,
        )

    with pytest.raises(ValueError):
        CompanyModuleStatus(
            definition=_DEFINITION,
            state=ModuleActivationState.DISABLED,
            version=1,
            activation_present=False,
            effective_enabled=False,
        )


def test_present_status_requires_positive_version_and_effective_state_match() -> None:
    with pytest.raises(ValueError):
        CompanyModuleStatus(
            definition=_DEFINITION,
            state=ModuleActivationState.DISABLED,
            version=0,
            activation_present=True,
            effective_enabled=False,
        )

    with pytest.raises(ValueError):
        CompanyModuleStatus(
            definition=_DEFINITION,
            state=ModuleActivationState.DISABLED,
            version=1,
            activation_present=True,
            effective_enabled=True,
        )


def test_activation_requires_timezone_with_real_offset() -> None:
    class NoOffsetTz(tzinfo):
        def utcoffset(self, dt):
            return None

        def dst(self, dt):
            return None

        def tzname(self, dt):
            return "NO-OFFSET"

    with pytest.raises(ValueError):
        CompanyModuleActivation(
            company_id=uuid4(),
            module_id="milking",
            state=ModuleActivationState.ENABLED,
            version=1,
            created_at=datetime(2026, 8, 26, 20, 0, tzinfo=NoOffsetTz()),
            created_by=uuid4(),
        )


def test_valid_present_status_accepts_enabled_and_disabled() -> None:
    enabled = CompanyModuleStatus(
        definition=_DEFINITION,
        state=ModuleActivationState.ENABLED,
        version=1,
        activation_present=True,
        effective_enabled=True,
    )
    disabled = CompanyModuleStatus(
        definition=_DEFINITION,
        state=ModuleActivationState.DISABLED,
        version=2,
        activation_present=True,
        effective_enabled=False,
    )
    assert enabled.effective_enabled
    assert not disabled.effective_enabled


def test_activation_accepts_utc_timestamp() -> None:
    activation = CompanyModuleActivation(
        company_id=uuid4(),
        module_id="milking",
        state=ModuleActivationState.ENABLED,
        version=1,
        created_at=datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc),
        created_by=uuid4(),
    )
    assert activation.version == 1
