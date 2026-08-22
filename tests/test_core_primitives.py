from datetime import timezone

import pytest

from app.core.config.settings import ConfigurationError, Settings
from app.core.identifiers.uuid import new_uuid
from app.core.time.clock import SystemClock


def test_settings_normalize_environment_and_hide_database_url_from_repr():
    settings = Settings(
        environment=" TEST ",
        database_url="postgresql://user:super-secret@db.example/erp",
        log_level="info",
    )

    assert settings.environment == "test"
    assert settings.log_level == "INFO"
    assert "super-secret" not in repr(settings)
    assert "postgresql://" not in repr(settings)


def test_settings_reject_unknown_environment():
    with pytest.raises(ConfigurationError):
        Settings(environment="unknown")


def test_new_uuid_returns_unique_values():
    assert new_uuid() != new_uuid()


def test_system_clock_returns_timezone_aware_utc_instant():
    instant = SystemClock().now()

    assert instant.tzinfo is not None
    assert instant.utcoffset() == timezone.utc.utcoffset(instant)
